from types import SimpleNamespace
import uuid

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from sesame_remo.crypto import SesameOS3Cipher, aes_cmac
from sesame_remo.sesame_client import (
    SesameOS3Client,
    parse_sesame5_advertisement,
)


def test_parse_sesame5_advertisement_selects_matching_manufacturer_payload() -> None:
    device_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    payload = bytes([5, 0, 3]) + device_id.bytes
    device = BLEDevice("test-address", "Sesame", details=None)
    advertisement = AdvertisementData(
        local_name="Sesame",
        manufacturer_data={0x0001: b"other", 0x055A: payload},
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=-50,
        platform_data=(),
    )

    parsed = parse_sesame5_advertisement(device, advertisement)

    assert parsed is not None
    assert parsed.device_id == device_id
    assert parsed.has_history
    assert parsed.is_registered
    assert parsed.product_type == 5


def test_client_rejects_wrong_secret_key_length() -> None:
    with pytest.raises(ValueError, match="16 bytes"):
        SesameOS3Client("12345678-1234-5678-1234-567812345678", "0011")


@pytest.mark.asyncio
async def test_consume_history_deletes_only_after_handler_succeeds(monkeypatch) -> None:
    secret = bytes.fromhex("00112233445566778899aabbccddeeff")
    token = bytes.fromhex("01020304")
    session_key = aes_cmac(secret, token)
    history_payload = bytes.fromhex("1122334402aabb")
    events: list[str] = []

    class FakeBleakClient:
        def __init__(self, _device: object, timeout: float) -> None:
            self.timeout = timeout
            self.callback = None
            self.peer_rx = SesameOS3Cipher(session_key, token)
            self.peer_tx = SesameOS3Cipher(session_key, token)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def start_notify(self, _uuid: str, callback) -> None:
            self.callback = callback
            callback(None, bytearray(b"\x03\x08\x0e" + token))

        async def write_gatt_char(
            self, _uuid: str, chunk: bytes, response: bool
        ) -> None:
            assert response is False
            assert self.callback is not None
            segment_type = chunk[0] >> 1
            if segment_type == 1:
                assert chunk[1] == 2
                self.callback(None, bytearray(b"\x03\x07\x02\x00"))
                return

            command = self.peer_rx.decrypt(chunk[1:])
            if command[0] == 4:
                response_payload = b"\x07\x04\x00" + history_payload
            elif command[0] == 18:
                events.append("delete")
                assert command[1:] == history_payload[:4]
                response_payload = b"\x07\x12\x00"
            else:
                raise AssertionError(f"unexpected command: {command.hex()}")
            encrypted = self.peer_tx.encrypt(response_payload)
            self.callback(None, bytearray(b"\x05" + encrypted))

    client = SesameOS3Client(str(uuid.uuid4()), secret.hex())

    async def fake_find(*, require_history: bool, scan_timeout: float):
        assert require_history
        assert scan_timeout == 1
        return SimpleNamespace(device=object(), is_registered=True)

    async def handler(record) -> None:
        events.append("handler")
        assert record.payload == history_payload

    monkeypatch.setattr("bleak.BleakClient", FakeBleakClient)
    monkeypatch.setattr(client, "find", fake_find)

    await client.consume_history_once(
        handler, scan_timeout=1, delete_after_success=True
    )

    assert events == ["handler", "delete"]


@pytest.mark.asyncio
async def test_read_status_does_not_require_pending_history(monkeypatch) -> None:
    secret = bytes.fromhex("00112233445566778899aabbccddeeff")
    token = bytes.fromhex("01020304")
    session_key = aes_cmac(secret, token)
    mech_status_payload = bytes.fromhex("00000000341202")

    class FakeBleakClient:
        def __init__(self, _device: object, timeout: float) -> None:
            self.timeout = timeout
            self.callback = None
            self.peer_rx = SesameOS3Cipher(session_key, token)
            self.peer_tx = SesameOS3Cipher(session_key, token)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def start_notify(self, _uuid: str, callback) -> None:
            self.callback = callback
            callback(None, bytearray(b"\x03\x08\x0e" + token))

        async def write_gatt_char(
            self, _uuid: str, chunk: bytes, response: bool
        ) -> None:
            assert response is False
            assert self.callback is not None
            command = chunk[1:]
            if chunk[0] >> 1 == 1:
                assert command[0] == 2
                self.callback(None, bytearray(b"\x03\x07\x02\x00"))
                status_publish = self.peer_tx.encrypt(b"\x08\x51" + mech_status_payload)
                self.callback(None, bytearray(b"\x05" + status_publish))
                return
            command = self.peer_rx.decrypt(command)
            assert command[0] == 2
            login_response = self.peer_tx.encrypt(b"\x07\x02\x00")
            self.callback(None, bytearray(b"\x05" + login_response))

    client = SesameOS3Client(str(uuid.uuid4()), secret.hex())

    async def fake_find(*, require_history: bool, scan_timeout: float):
        assert not require_history
        assert scan_timeout == 1
        return SimpleNamespace(device=object(), is_registered=True)

    monkeypatch.setattr("bleak.BleakClient", FakeBleakClient)
    monkeypatch.setattr(client, "find", fake_find)

    status = await client.read_status_once(scan_timeout=1)

    assert status.is_locked
    assert status.position == 0x1234


@pytest.mark.asyncio
async def test_monitor_status_keeps_connection_for_publish_notifications(
    monkeypatch,
) -> None:
    secret = bytes.fromhex("00112233445566778899aabbccddeeff")
    token = bytes.fromhex("01020304")
    session_key = aes_cmac(secret, token)
    mech_status_payload = bytes.fromhex("00000000341200")
    connection_count = 0

    class StopMonitor(Exception):
        pass

    class FakeBleakClient:
        def __init__(self, _device: object, timeout: float) -> None:
            nonlocal connection_count
            connection_count += 1
            self.is_connected = True
            self.callback = None
            self.peer_tx = SesameOS3Cipher(session_key, token)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def start_notify(self, _uuid: str, callback) -> None:
            self.callback = callback
            callback(None, bytearray(b"\x03\x08\x0e" + token))

        async def write_gatt_char(
            self, _uuid: str, chunk: bytes, response: bool
        ) -> None:
            assert response is False
            assert self.callback is not None
            assert chunk[0] >> 1 == 1
            assert chunk[1] == 2
            self.callback(None, bytearray(b"\x03\x07\x02\x00"))
            status_publish = self.peer_tx.encrypt(b"\x08\x51" + mech_status_payload)
            self.callback(None, bytearray(b"\x05" + status_publish))

    client = SesameOS3Client(str(uuid.uuid4()), secret.hex())

    class FakeBleakScanner:
        def __init__(self, callback, service_uuids) -> None:
            self.callback = callback

        async def start(self) -> None:
            device = BLEDevice("test-address", "Sesame", details=None)
            payload = bytes([5, 0, 1]) + client.sesame_id.bytes
            advertisement = AdvertisementData(
                local_name="Sesame",
                manufacturer_data={0x055A: payload},
                service_data={},
                service_uuids=[],
                tx_power=None,
                rssi=-50,
                platform_data=(),
            )
            self.callback(device, advertisement)

        async def stop(self) -> None:
            return None

    async def handler(status) -> None:
        assert status.is_unlocked
        raise StopMonitor

    monkeypatch.setattr("bleak.BleakClient", FakeBleakClient)
    monkeypatch.setattr("bleak.BleakScanner", FakeBleakScanner)

    with pytest.raises(StopMonitor):
        await client.monitor_status(handler, scan_timeout=1)

    assert connection_count == 1
