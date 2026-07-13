from sesame_remo.ble_protocol import (
    ItemCode,
    SegmentType,
    SesameBleReceiver,
    SesameResponse,
    chunks_for_transmit,
    command_payload,
    parse_plain_notify,
)
from sesame_remo.crypto import counter_bytes


def test_command_payload_prefixes_item_code() -> None:
    assert command_payload(ItemCode.HISTORY, b"\x01") == b"\x04\x01"


def test_chunks_for_transmit_single_plain_segment() -> None:
    assert chunks_for_transmit(SegmentType.PLAIN, b"abc") == [b"\x03abc"]


def test_chunks_for_transmit_multiple_segments() -> None:
    payload = bytes(range(25))
    chunks = chunks_for_transmit(SegmentType.CIPHER, payload)
    assert chunks == [
        b"\x01" + bytes(range(19)),
        b"\x04" + bytes(range(19, 25)),
    ]


def test_receiver_reassembles_segments() -> None:
    receiver = SesameBleReceiver()
    assert receiver.feed(b"\x01abc") is None
    assert receiver.feed(b"\x04def") == (SegmentType.CIPHER, b"abcdef")


def test_parse_response_notify() -> None:
    parsed = parse_plain_notify(b"\x07\x04\x00payload")
    assert parsed == SesameResponse(item_code=4, result_code=0, payload=b"payload")


def test_counter_bytes_matches_sdk_little_endian_long() -> None:
    assert counter_bytes(1) == b"\x01\x00\x00\x00\x00\x00\x00\x00"

