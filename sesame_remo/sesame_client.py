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


@dataclass(frozen=True)
class SesameAdvertisement:
    device: BLEDevice
    device_id: uuid.UUID
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
        self._responses: dict[int, asyncio.Future[SesameResponse]] = {}
        self._fatal_error: BaseException | None = None

        if len(self.secret_key) != 16:
            raise ValueError("secret key must be exactly 16 bytes")

    async def find(self, scan_timeout: float = 10.0) -> SesameAdvertisement:
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
            found.set_result(parsed)

        scanner = BleakScanner(callback, service_uuids=[SESAME_SERVICE_UUID])
        await scanner.start()
        try:
            try:
                return await asyncio.wait_for(found, timeout=scan_timeout)
            except TimeoutError as exc:
                raise SesameScanTimeout(
                    f"timed out after {scan_timeout:g}s waiting for Sesame5 "
                    f"{self.sesame_id}; check the UUID, Bluetooth permission, and distance"
                ) from exc
        finally:
            await scanner.stop()

    async def read_status_once(
        self, scan_timeout: float = 10.0
    ) -> Sesame5MechanismStatus:
        """Read the current lock state."""
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
    ) -> None:
        """Keep scanning and reconnect when a Sesame advertisement is received."""
        from bleak import BleakScanner

        advertisements: asyncio.Queue[SesameAdvertisement] = asyncio.Queue(maxsize=1)
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
                try:
                    connection_active = True
                    if connection_event_handler is not None:
                        await connection_event_handler("connected")
                    queue = self._require_status_queue()
                    status_task = asyncio.create_task(
                        self._monitor_status_current_connection(handler, queue)
                    )
                    try:
                        await status_task
                    except SesameConnectionLost:
                        connection_lost = True
                finally:
                    if status_task is not None:
                        status_task.cancel()
                        await asyncio.gather(status_task, return_exceptions=True)
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
    ) -> AsyncIterator[None]:
        from bleak import BleakClient

        adv = advertisement or await self.find(scan_timeout=scan_timeout)
        if not adv.is_registered:
            raise RuntimeError("Sesame5 is not registered")
        async with BleakClient(adv.device, timeout=self.timeout) as client:
            self._client = client
            self._receiver = SesameBleReceiver()
            self._cipher = None
            self._initial_token = asyncio.get_running_loop().create_future()
            self._mechanism_status_queue = asyncio.Queue()
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
                yield
            finally:
                self._mechanism_status_queue = None
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
