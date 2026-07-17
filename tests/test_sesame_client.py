import uuid

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from sesame_remo.sesame_client import SesameOS3Client, parse_sesame5_advertisement
from sesame_remo.crypto import SesameOS3Cipher, aes_cmac


def test_parse_sesame5_advertisement_selects_registered_device() -> None:
    device_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    payload = bytes([5, 0, 1]) + device_id.bytes
    device = BLEDevice("test-address", "Sesame", details=None)
    advertisement = AdvertisementData(
        local_name="Sesame",
        manufacturer_data={0x055A: payload},
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=-50,
        platform_data=(),
    )

    parsed = parse_sesame5_advertisement(device, advertisement)

    assert parsed is not None
    assert parsed.device_id == device_id
    assert parsed.is_registered
    assert parsed.product_type == 5
    assert not hasattr(parsed, "has_history")


def test_client_rejects_wrong_secret_key_length() -> None:
    with pytest.raises(ValueError, match="16 bytes"):
        SesameOS3Client("12345678-1234-5678-1234-567812345678", "0011")


@pytest.mark.asyncio
async def test_monitor_status_reconnects_only_from_fresh_advertisement(
    monkeypatch,
) -> None:
    secret = bytes.fromhex("00112233445566778899aabbccddeeff")
    token = bytes.fromhex("01020304")
    session_key = aes_cmac(secret, token)
    mech_status_payload = bytes.fromhex("00000000341200")
    connection_count = 0
    current_connection = None
    scanner_callback = None
    status_count = 0
    connection_devices: list[BLEDevice] = []

    class StopMonitor(Exception):
        pass

    class FakeBleakClient:
        def __init__(self, device: object, timeout: float) -> None:
            nonlocal connection_count, current_connection
            connection_count += 1
            current_connection = self
            assert isinstance(device, BLEDevice)
            connection_devices.append(device)
            self.is_connected = True
            self.callback = None
            self.peer_tx = SesameOS3Cipher(session_key, token)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            if connection_count == 1:
                assert scanner_callback is not None
                scanner_callback(
                    BLEDevice("stale-address", "stale", details=None),
                    _advertisement(client, "Sesame"),
                )

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
            nonlocal scanner_callback
            self.callback = callback
            scanner_callback = callback

        async def start(self) -> None:
            self.callback(
                BLEDevice("test-address", "Sesame", details=None),
                _advertisement(client, "Sesame"),
            )

        async def stop(self) -> None:
            return None

    async def handler(status) -> None:
        nonlocal status_count
        assert status.is_unlocked
        status_count += 1
        if status_count == 1:
            assert current_connection is not None
            assert scanner_callback is not None
            scanner_callback(
                BLEDevice("active-address", "active", details=None),
                _advertisement(client, "Sesame"),
            )
            current_connection.is_connected = False
        else:
            raise StopMonitor

    async def connection_event_handler(event: str) -> None:
        if event != "connection_lost":
            return
        assert scanner_callback is not None
        scanner_callback(
            BLEDevice("fresh-address", "fresh", details=None),
            _advertisement(client, "fresh"),
        )

    monkeypatch.setattr("bleak.BleakClient", FakeBleakClient)
    monkeypatch.setattr("bleak.BleakScanner", FakeBleakScanner)

    with pytest.raises(StopMonitor):
        await client.monitor_status(
            handler,
            scan_timeout=1,
            connection_event_handler=connection_event_handler,
        )

    assert connection_count == 2
    assert connection_devices[1].name == "fresh"


def _advertisement(client: SesameOS3Client, local_name: str) -> AdvertisementData:
    return AdvertisementData(
        local_name=local_name,
        manufacturer_data={0x055A: bytes([5, 0, 1]) + client.sesame_id.bytes},
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=-50,
        platform_data=(),
    )
