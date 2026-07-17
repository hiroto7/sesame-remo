import uuid

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from sesame_remo.sesame_client import SesameOS3Client, parse_sesame5_advertisement


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
