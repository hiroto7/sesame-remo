from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SegmentType(IntEnum):
    PLAIN = 1
    CIPHER = 2


class OpCode(IntEnum):
    RESPONSE = 0x07
    PUBLISH = 0x08


class ItemCode(IntEnum):
    LOGIN = 2
    INITIAL = 14


@dataclass(frozen=True)
class SesameResponse:
    item_code: int
    result_code: int
    payload: bytes


@dataclass(frozen=True)
class SesamePublish:
    item_code: int
    payload: bytes


class SesameBleReceiver:
    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> tuple[SegmentType, bytes] | None:
        if not data:
            raise ValueError("empty BLE segment")
        segment_flag = data[0]
        is_start = segment_flag & 1
        parsing_type = segment_flag >> 1
        if is_start:
            self._buffer = data[1:]
        else:
            self._buffer += data[1:]
        if parsing_type > 0:
            payload = self._buffer
            self._buffer = b""
            return SegmentType(parsing_type), payload
        return None


def chunks_for_transmit(segment_type: SegmentType, payload: bytes) -> list[bytes]:
    chunks: list[bytes] = []
    is_start = 1
    remaining = payload
    while True:
        if len(remaining) <= 19:
            segment_header = (segment_type.value << 1) | is_start
            chunks.append(bytes([segment_header]) + remaining)
            return chunks
        chunks.append(bytes([is_start]) + remaining[:19])
        remaining = remaining[19:]
        is_start = 0


def command_payload(item_code: ItemCode, data: bytes = b"") -> bytes:
    return bytes([item_code.value]) + data


def parse_plain_notify(plaintext: bytes) -> SesameResponse | SesamePublish:
    if not plaintext:
        raise ValueError("empty Sesame notification")
    op = plaintext[0]
    payload = plaintext[1:]
    if op == OpCode.RESPONSE:
        if len(payload) < 2:
            raise ValueError("truncated Sesame response")
        return SesameResponse(payload[0], payload[1], payload[2:])
    if op == OpCode.PUBLISH:
        if not payload:
            raise ValueError("truncated Sesame publish")
        return SesamePublish(payload[0], payload[1:])
    raise ValueError(f"unsupported notify opcode: 0x{op:02x}")
