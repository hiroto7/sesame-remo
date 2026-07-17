from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator
import uuid

from .ble_protocol import (
    ItemCode,
    SesameBleReceiver,
    SesamePublish,
    SesameResponse,
    SegmentType,
    chunks_for_transmit,
    command_payload,
    parse_plain_notify,
)
from .crypto import SesameOS3Cipher, aes_cmac
from .history import HistoryRecord
from .status import Sesame5MechanismStatus, is_mech_status_publish

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
else:
    BLEDevice = object
    AdvertisementData = object


SESAME_SERVICE_UUID = "0000fd81-0000-1000-8000-00805f9b34fb"
SESAME_WRITE_UUID = "16860002-a5ae-9856-b6d3-dbb4c676993e"
SESAME_NOTIFY_UUID = "16860003-a5ae-9856-b6d3-dbb4c676993e"
SESAME5_PRODUCT_TYPES = {5, 7, 16}


class SesameScanTimeout(TimeoutError):
    pass


class SesameConnectionLost(ConnectionError):
    pass


MonitorEventHandler = Callable[[str, dict[str, object]], Awaitable[None]]
StatusEventHandler = Callable[[Sesame5MechanismStatus], None]


@dataclass(frozen=True)
class SesameAdvertisement:
    device: BLEDevice
    device_id: uuid.UUID
    has_history: bool
    is_registered: bool
    product_type: int


def _normalize_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value.replace("-", ""))


def _manufacturer_payload(advertisement_data: AdvertisementData) -> bytes | None:
    for payload in advertisement_data.manufacturer_data.values():
        if len(payload) >= 19 and payload[0] in SESAME5_PRODUCT_TYPES:
            return payload
    return None


def parse_sesame5_advertisement(
    device: BLEDevice, advertisement_data: AdvertisementData
) -> SesameAdvertisement | None:
    adv = _manufacturer_payload(advertisement_data)
    if adv is None or len(adv) < 19:
        return None
    product_type = adv[0]
    if product_type not in SESAME5_PRODUCT_TYPES:
        return None
    device_id = uuid.UUID(bytes=adv[3:19])
    return SesameAdvertisement(
        device=device,
        device_id=device_id,
        has_history=(adv[2] & 0x02) > 0,
        is_registered=(adv[2] & 0x01) > 0,
        product_type=product_type,
    )


class SesameOS3Client:
    def __init__(
        self, sesame_id: str, secret_key_hex: str, timeout: float = 15.0
    ) -> None:
        self.sesame_id = _normalize_uuid(sesame_id)
        self.secret_key = bytes.fromhex(secret_key_hex)
        self.timeout = timeout
        self._client: BleakClient | None = None
        self._receiver = SesameBleReceiver()
        self._cipher: SesameOS3Cipher | None = None
        self._initial_token: asyncio.Future[bytes] | None = None
        self._mechanism_status_queue: asyncio.Queue[Sesame5MechanismStatus] | None = (
            None
        )
        self._status_event_handler: StatusEventHandler | None = None
        self._responses: dict[int, asyncio.Future[SesameResponse]] = {}
        self._fatal_error: BaseException | None = None

        if len(self.secret_key) != 16:
            raise ValueError("secret key must be exactly 16 bytes")

    async def find(
        self, require_history: bool, scan_timeout: float = 10.0
    ) -> SesameAdvertisement:
        from bleak import BleakScanner

        found: asyncio.Future[SesameAdvertisement] = (
            asyncio.get_running_loop().create_future()
        )

        def callback(device: BLEDevice, advertisement_data: AdvertisementData) -> None:
            if found.done():
                return
            parsed = parse_sesame5_advertisement(device, advertisement_data)
            if parsed is None or parsed.device_id != self.sesame_id:
                return
            if require_history and not parsed.has_history:
                return
            found.set_result(parsed)

        scanner = BleakScanner(callback, service_uuids=[SESAME_SERVICE_UUID])
        await scanner.start()
        try:
            try:
                return await asyncio.wait_for(found, timeout=scan_timeout)
            except TimeoutError as exc:
                requirement = " with pending history" if require_history else ""
                raise SesameScanTimeout(
                    f"timed out after {scan_timeout:g}s waiting for Sesame5 "
                    f"{self.sesame_id}{requirement}; check the UUID, Bluetooth permission, "
                    "distance, and generate a new lock history event"
                ) from exc
        finally:
            await scanner.stop()

    async def read_history_once(
        self, scan_timeout: float = 10.0, delete_after_read: bool = False
    ) -> HistoryRecord:
        async def no_op(_record: HistoryRecord) -> None:
            return None

        return await self.consume_history_once(
            no_op,
            scan_timeout=scan_timeout,
            delete_after_success=delete_after_read,
        )

    async def read_status_once(
        self, scan_timeout: float = 10.0
    ) -> Sesame5MechanismStatus:
        """Read the current lock state without reading or deleting history."""
        async with self._logged_in(scan_timeout=scan_timeout):
            queue = self._require_status_queue()
            return await self._next_status(queue)

    async def monitor_status(
        self,
        handler: Callable[[Sesame5MechanismStatus], Awaitable[None]],
        *,
        scan_timeout: float = 10.0,
        connection_lost_handler: Callable[[], Awaitable[None]] | None = None,
        connection_event_handler: Callable[[str], Awaitable[None]] | None = None,
        history_handler: Callable[[HistoryRecord], Awaitable[None]] | None = None,
        history_event_handler: MonitorEventHandler | None = None,
    ) -> None:
        """Keep scanning and reconnect when a Sesame advertisement is received."""
        from bleak import BleakScanner

        advertisements: asyncio.Queue[SesameAdvertisement] = asyncio.Queue(maxsize=1)
        history_available: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        connection_active = False

        def discard_queued_advertisements() -> None:
            while True:
                try:
                    advertisements.get_nowait()
                except asyncio.QueueEmpty:
                    return

        def callback(device: BLEDevice, advertisement_data: AdvertisementData) -> None:
            parsed = parse_sesame5_advertisement(device, advertisement_data)
            if (
                parsed is None
                or parsed.device_id != self.sesame_id
                or not parsed.is_registered
            ):
                return
            if parsed.has_history:
                try:
                    history_available.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            if connection_active:
                return
            try:
                advertisements.put_nowait(parsed)
            except asyncio.QueueFull:
                pass

        scanner = BleakScanner(callback, service_uuids=[SESAME_SERVICE_UUID])
        await scanner.start()
        if connection_event_handler is not None:
            await connection_event_handler("scan_started")
        try:
            while True:
                try:
                    advertisement = await asyncio.wait_for(
                        advertisements.get(), timeout=scan_timeout
                    )
                except TimeoutError as exc:
                    if connection_event_handler is not None:
                        await connection_event_handler("scan_timeout")
                    raise SesameScanTimeout(
                        f"timed out after {scan_timeout:g}s waiting for Sesame5 "
                        f"{self.sesame_id}; check the UUID, Bluetooth permission, "
                        "and distance"
                    ) from exc

                connection = self._logged_in(
                    scan_timeout=scan_timeout,
                    advertisement=advertisement,
                )
                if connection_event_handler is not None:
                    await connection_event_handler("advertisement_received")
                    await connection_event_handler("connection_attempt")
                try:
                    await connection.__aenter__()
                except Exception:
                    # Keep the scanner alive. The next advertisement is the
                    # reconnect trigger, just like the official SDKs.
                    if connection_event_handler is not None:
                        await connection_event_handler("connection_failed")
                    if connection_lost_handler is not None:
                        await connection_lost_handler()
                    discard_queued_advertisements()
                    continue

                connection_lost = False
                status_task: asyncio.Task[None] | None = None
                history_task: asyncio.Task[None] | None = None
                try:
                    connection_active = True
                    if connection_event_handler is not None:
                        await connection_event_handler("connected")
                    if history_handler is not None:
                        history_task = asyncio.create_task(
                            self._poll_history_current_connection(
                                history_handler,
                                event_handler=history_event_handler,
                                history_available=history_available,
                            )
                        )
                    queue = self._require_status_queue()
                    try:
                        status_task = asyncio.create_task(
                            self._monitor_status_current_connection(handler, queue)
                        )
                        tasks = {status_task}
                        if history_task is not None:
                            tasks.add(history_task)
                        done, _pending = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_EXCEPTION
                        )
                        for task in done:
                            task.result()
                    except SesameConnectionLost:
                        # A real BLE disconnect is replaced by the next advert.
                        connection_lost = True
                finally:
                    for task in (status_task, history_task):
                        if task is not None:
                            task.cancel()
                    await asyncio.gather(
                        *(
                            task
                            for task in (status_task, history_task)
                            if task is not None
                        ),
                        return_exceptions=True,
                    )
                    try:
                        await connection.__aexit__(None, None, None)
                    finally:
                        connection_active = False
                        discard_queued_advertisements()
                if connection_lost:
                    if connection_event_handler is not None:
                        await connection_event_handler("connection_lost")
                    if connection_lost_handler is not None:
                        await connection_lost_handler()
        finally:
            await scanner.stop()
            if connection_event_handler is not None:
                await connection_event_handler("scan_stopped")

    async def _monitor_status_current_connection(
        self,
        handler: Callable[[Sesame5MechanismStatus], Awaitable[None]],
        queue: asyncio.Queue[Sesame5MechanismStatus],
    ) -> None:
        while True:
            await handler(await self._next_status_until_disconnected(queue))

    @asynccontextmanager
    async def _logged_in(
        self,
        *,
        scan_timeout: float,
        advertisement: SesameAdvertisement | None = None,
        require_history: bool = False,
        event_handler: MonitorEventHandler | None = None,
        status_event_handler: StatusEventHandler | None = None,
    ) -> AsyncIterator[None]:
        from bleak import BleakClient

        adv = advertisement or await self.find(
            require_history=require_history, scan_timeout=scan_timeout
        )
        if not adv.is_registered:
            raise RuntimeError("Sesame5 is not registered")
        async with BleakClient(adv.device, timeout=self.timeout) as client:
            self._client = client
            self._receiver = SesameBleReceiver()
            self._cipher = None
            self._initial_token = asyncio.get_running_loop().create_future()
            self._mechanism_status_queue = asyncio.Queue()
            self._status_event_handler = status_event_handler
            self._responses = {}
            self._fatal_error = None
            try:
                await client.start_notify(SESAME_NOTIFY_UUID, self._on_notify)
                token = await asyncio.wait_for(
                    self._initial_token, timeout=self.timeout
                )
                if len(token) != 4:
                    raise RuntimeError(f"unexpected Sesame token length: {len(token)}")
                session_auth = aes_cmac(self.secret_key, token)
                self._cipher = SesameOS3Cipher(session_auth, token)
                login = await self._send_plain_with_response(
                    ItemCode.LOGIN, session_auth[:4]
                )
                self._require_success(login, "login")
                if event_handler is not None:
                    await event_handler("connected", {})
                yield
            finally:
                self._mechanism_status_queue = None
                self._status_event_handler = None
                self._client = None

    async def _next_status(
        self, queue: asyncio.Queue[Sesame5MechanismStatus]
    ) -> Sesame5MechanismStatus:
        try:
            return await asyncio.wait_for(queue.get(), timeout=self.timeout)
        except TimeoutError as exc:
            raise SesameScanTimeout(
                f"timed out after {self.timeout:g}s waiting for Sesame5 mechStatus"
            ) from exc

    async def _next_status_until_disconnected(
        self, queue: asyncio.Queue[Sesame5MechanismStatus]
    ) -> Sesame5MechanismStatus:
        while True:
            client = self._client
            if client is None or not client.is_connected:
                raise SesameConnectionLost("Sesame BLE connection was lost")
            try:
                return await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                continue

    def _require_status_queue(self) -> asyncio.Queue[Sesame5MechanismStatus]:
        if self._mechanism_status_queue is None:
            raise RuntimeError("status monitor is not connected")
        return self._mechanism_status_queue

    async def _poll_history_current_connection(
        self,
        handler: Callable[[HistoryRecord], Awaitable[None]],
        *,
        event_handler: MonitorEventHandler | None,
        history_available: asyncio.Queue[None],
    ) -> None:
        while True:
            await history_available.get()
            record = await self.read_history_current_connection(
                handler,
                event_handler=event_handler,
            )
            if record is None:
                continue

    async def read_history_current_connection(
        self,
        handler: Callable[[HistoryRecord], Awaitable[None]],
        *,
        delete_after_success: bool = True,
        event_handler: MonitorEventHandler | None = None,
    ) -> HistoryRecord | None:
        """Read one history record using the already authenticated BLE session."""
        if self._cipher is None:
            raise RuntimeError("not logged in")
        if event_handler is not None:
            await event_handler("history_requested", {})
        response = await self._send_cipher(ItemCode.HISTORY, b"\x01")
        if response.result_code != 0:
            return None
        record = HistoryRecord(response.payload)
        if event_handler is not None:
            await event_handler(
                "history_received",
                {
                    "record_id": record.record_id,
                    "event_type": record.event_type,
                    "is_unlock": record.is_unlock,
                },
            )
        await handler(record)
        if delete_after_success:
            await self.delete_history(record.record_id)
            if event_handler is not None:
                await event_handler("history_deleted", {"record_id": record.record_id})
        return record

    async def consume_history_once(
        self,
        handler: Callable[[HistoryRecord], Awaitable[None]],
        *,
        scan_timeout: float = 10.0,
        delete_after_success: bool = True,
        event_handler: MonitorEventHandler | None = None,
        status_event_handler: StatusEventHandler | None = None,
    ) -> HistoryRecord:
        """Read one history record and delete it only after handler succeeds."""
        adv = await self.find(require_history=True, scan_timeout=scan_timeout)
        if event_handler is not None:
            await event_handler(
                "advertisement_received",
                {"has_history": adv.has_history, "product_type": adv.product_type},
            )
        if not adv.is_registered:
            raise RuntimeError("Sesame5 is not registered")
        if event_handler is not None:
            await event_handler("connection_attempt", {})
        async with self._logged_in(
            scan_timeout=scan_timeout,
            advertisement=adv,
            event_handler=event_handler,
            status_event_handler=status_event_handler,
        ):
            record = await self.read_history_current_connection(
                handler,
                delete_after_success=delete_after_success,
                event_handler=event_handler,
            )
            if record is None:
                raise RuntimeError("history returned no record")
            return record

    async def delete_history(self, record_id_hex: str) -> None:
        response = await self._send_cipher(
            ItemCode.HISTORY_DELETE, bytes.fromhex(record_id_hex)
        )
        self._require_success(response, "history delete")

    @staticmethod
    def _require_success(response: SesameResponse, command: str) -> None:
        if response.result_code != 0:
            raise RuntimeError(f"{command} failed: result_code={response.result_code}")

    async def _send_plain_with_response(
        self, item_code: ItemCode, data: bytes = b""
    ) -> SesameResponse:
        future = self._new_response_future(item_code)
        await self._write_segmented(SegmentType.PLAIN, command_payload(item_code, data))
        return await self._await_response(item_code, future)

    async def _send_cipher(
        self, item_code: ItemCode, data: bytes = b""
    ) -> SesameResponse:
        if self._cipher is None:
            raise RuntimeError("not logged in")
        payload = self._cipher.encrypt(command_payload(item_code, data))
        future = self._new_response_future(item_code)
        await self._write_segmented(SegmentType.CIPHER, payload)
        return await self._await_response(item_code, future)

    def _new_response_future(
        self, item_code: ItemCode
    ) -> asyncio.Future[SesameResponse]:
        if self._fatal_error is not None:
            raise RuntimeError("Sesame BLE protocol failed") from self._fatal_error
        existing = self._responses.get(item_code.value)
        if existing is not None and not existing.done():
            raise RuntimeError(f"command already pending: item_code={item_code.value}")
        future: asyncio.Future[SesameResponse] = (
            asyncio.get_running_loop().create_future()
        )
        self._responses[item_code.value] = future
        return future

    async def _await_response(
        self, item_code: ItemCode, future: asyncio.Future[SesameResponse]
    ) -> SesameResponse:
        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        finally:
            if self._responses.get(item_code.value) is future:
                self._responses.pop(item_code.value, None)

    async def _write_segmented(self, segment_type: SegmentType, payload: bytes) -> None:
        if self._client is None:
            raise RuntimeError("not connected")
        for chunk in chunks_for_transmit(segment_type, payload):
            await self._client.write_gatt_char(SESAME_WRITE_UUID, chunk, response=False)

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        try:
            completed = self._receiver.feed(bytes(data))
            if completed is None:
                return
            segment_type, payload = completed
            if segment_type == SegmentType.CIPHER:
                if self._cipher is None:
                    raise RuntimeError("received cipher payload before cipher setup")
                payload = self._cipher.decrypt(payload)
            parsed = parse_plain_notify(payload)
            if isinstance(parsed, SesamePublish):
                if (
                    parsed.item_code == ItemCode.INITIAL
                    and self._initial_token
                    and not self._initial_token.done()
                ):
                    self._initial_token.set_result(parsed.payload)
                elif is_mech_status_publish(parsed.item_code):
                    if self._mechanism_status_queue is not None:
                        self._mechanism_status_queue.put_nowait(
                            Sesame5MechanismStatus(parsed.payload)
                        )
                    if self._status_event_handler is not None:
                        self._status_event_handler(
                            Sesame5MechanismStatus(parsed.payload)
                        )
                return
            if isinstance(parsed, SesameResponse):
                future = self._responses.get(parsed.item_code)
                if future is not None and not future.done():
                    future.set_result(parsed)
        except Exception as exc:
            self._fail_pending(exc)

    def _fail_pending(self, exc: BaseException) -> None:
        self._fatal_error = exc
        if self._initial_token is not None and not self._initial_token.done():
            self._initial_token.set_exception(exc)
        for future in self._responses.values():
            if not future.done():
                future.set_exception(exc)
