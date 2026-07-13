from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING
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

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
else:
    BLEDevice = object
    AdvertisementData = object


SESAME_SERVICE_UUID = "0000fd81-0000-1000-8000-00805f9b34fb"
SESAME_WRITE_UUID = "16860002-a5ae-9856-b6d3-dbb4c676993e"
SESAME_NOTIFY_UUID = "16860003-a5ae-9856-b6d3-dbb4c676993e"
SESAME5_PRODUCT_TYPES = {5, 7, 16}


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
    if not advertisement_data.manufacturer_data:
        return None
    return next(iter(advertisement_data.manufacturer_data.values()))


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
    def __init__(self, sesame_id: str, secret_key_hex: str, timeout: float = 15.0) -> None:
        self.sesame_id = _normalize_uuid(sesame_id)
        self.secret_key = bytes.fromhex(secret_key_hex)
        self.timeout = timeout
        self._client: BleakClient | None = None
        self._receiver = SesameBleReceiver()
        self._cipher: SesameOS3Cipher | None = None
        self._initial_token: asyncio.Future[bytes] | None = None
        self._responses: dict[int, asyncio.Future[SesameResponse]] = {}

    async def find(self, require_history: bool, scan_timeout: float = 10.0) -> SesameAdvertisement:
        from bleak import BleakScanner

        found: asyncio.Future[SesameAdvertisement] = asyncio.get_running_loop().create_future()

        def callback(device: BLEDevice, advertisement_data: AdvertisementData) -> None:
            if found.done():
                return
            parsed = parse_sesame5_advertisement(device, advertisement_data)
            if parsed is None or parsed.device_id != self.sesame_id:
                return
            if require_history and not parsed.has_history:
                return
            found.set_result(parsed)

        scanner = BleakScanner(callback)
        await scanner.start()
        try:
            return await asyncio.wait_for(found, timeout=scan_timeout)
        finally:
            await scanner.stop()

    async def read_history_once(
        self, scan_timeout: float = 10.0, delete_after_read: bool = False
    ) -> HistoryRecord:
        from bleak import BleakClient

        adv = await self.find(require_history=True, scan_timeout=scan_timeout)
        async with BleakClient(adv.device, timeout=self.timeout) as client:
            self._client = client
            self._receiver = SesameBleReceiver()
            self._cipher = None
            self._initial_token = asyncio.get_running_loop().create_future()
            self._responses = {}
            await client.start_notify(SESAME_NOTIFY_UUID, self._on_notify)
            token = await asyncio.wait_for(self._initial_token, timeout=self.timeout)
            session_auth = aes_cmac(self.secret_key, token)
            self._cipher = SesameOS3Cipher(session_auth, token)
            login_future = asyncio.get_running_loop().create_future()
            self._responses[ItemCode.LOGIN.value] = login_future
            await self._send_plain(ItemCode.LOGIN, session_auth[:4])
            await asyncio.wait_for(login_future, timeout=self.timeout)
            response = await self._send_cipher(ItemCode.HISTORY, b"\x01")
            if response.result_code != 0:
                raise RuntimeError(f"history command failed: result_code={response.result_code}")
            record = HistoryRecord(response.payload)
            if delete_after_read:
                await self.delete_history(record.record_id)
            return record

    async def delete_history(self, record_id_hex: str) -> None:
        response = await self._send_cipher(ItemCode.HISTORY_DELETE, bytes.fromhex(record_id_hex))
        if response.result_code != 0:
            raise RuntimeError(f"history delete failed: result_code={response.result_code}")

    async def _send_plain(self, item_code: ItemCode, data: bytes = b"") -> None:
        await self._write_segmented(SegmentType.PLAIN, command_payload(item_code, data))

    async def _send_cipher(self, item_code: ItemCode, data: bytes = b"") -> SesameResponse:
        if self._cipher is None:
            raise RuntimeError("not logged in")
        payload = self._cipher.encrypt(command_payload(item_code, data))
        future = asyncio.get_running_loop().create_future()
        self._responses[item_code.value] = future
        await self._write_segmented(SegmentType.CIPHER, payload)
        return await asyncio.wait_for(future, timeout=self.timeout)

    async def _wait_response(self, item_code: ItemCode) -> SesameResponse:
        future = self._responses.get(item_code.value)
        if future is None:
            future = asyncio.get_running_loop().create_future()
            self._responses[item_code.value] = future
        return await asyncio.wait_for(future, timeout=self.timeout)

    async def _write_segmented(self, segment_type: SegmentType, payload: bytes) -> None:
        if self._client is None:
            raise RuntimeError("not connected")
        for chunk in chunks_for_transmit(segment_type, payload):
            await self._client.write_gatt_char(SESAME_WRITE_UUID, chunk, response=False)

    def _on_notify(self, _sender: object, data: bytearray) -> None:
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
            if parsed.item_code == ItemCode.INITIAL and self._initial_token and not self._initial_token.done():
                self._initial_token.set_result(parsed.payload)
            return
        if isinstance(parsed, SesameResponse):
            future = self._responses.get(parsed.item_code)
            if future is not None and not future.done():
                future.set_result(parsed)
