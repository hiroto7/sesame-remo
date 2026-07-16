from __future__ import annotations

from dataclasses import dataclass
import json


MECH_STATUS_ITEM_CODE = 81


@dataclass(frozen=True)
class Sesame5MechanismStatus:
    """The lock state reported by Sesame5's OS3 mechStatus publish."""

    payload: bytes

    def __post_init__(self) -> None:
        if len(self.payload) < 7:
            raise ValueError("Sesame5 mechStatus payload must contain at least 7 bytes")

    @property
    def is_locked(self) -> bool:
        return bool(self.payload[6] & 0x02)

    @property
    def is_unlocked(self) -> bool:
        return not self.is_locked

    @property
    def position(self) -> int:
        return int.from_bytes(self.payload[4:6], byteorder="little", signed=True)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "is_locked": self.is_locked,
            "is_unlocked": self.is_unlocked,
            "position": self.position,
            "payload_hex": self.payload.hex(),
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_json_dict(), ensure_ascii=False)


def is_mech_status_publish(item_code: int) -> bool:
    return item_code == MECH_STATUS_ITEM_CODE
