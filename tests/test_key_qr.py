from base64 import b64encode
import uuid

import pytest

from sesame_remo.key_qr import decode_sesame5_share_url


def test_decode_sesame5_share_url() -> None:
    device_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    secret = bytes.fromhex("112233445566778899aabbccddeeff01")
    payload = bytes([5]) + secret + b"pubk" + b"\x00\x00" + device_id.bytes
    encoded = b64encode(payload).decode()

    key = decode_sesame5_share_url(f"ssm://UI?t=sk&sk={encoded}&l=0")

    assert key.device_id == device_id
    assert key.secret_key == secret


def test_decode_sesame5_share_url_rejects_guest_key() -> None:
    device_id = uuid.UUID(bytes=bytes(range(16)))
    payload = bytes([5]) + bytes(16) + b"pubk" + b"\x00\x00" + device_id.bytes
    encoded = b64encode(payload).decode()

    with pytest.raises(ValueError, match="guest keys"):
        decode_sesame5_share_url(f"ssm://UI?t=sk&sk={encoded}&l=2")


def test_decode_sesame5_share_url_accepts_unescaped_plus_in_base64() -> None:
    device_id = uuid.UUID(bytes=bytes(range(16)))
    secret = bytes([62]) * 16
    payload = bytes([5]) + secret + b"pubk" + b"\x00\x00" + device_id.bytes
    encoded = b64encode(payload).decode()
    assert "+" in encoded

    key = decode_sesame5_share_url(f"ssm://UI?t=sk&sk={encoded}&l=0")

    assert key.secret_key == secret
