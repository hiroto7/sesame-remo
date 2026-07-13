from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
import json

from .config import TouchProMatch


class HistoryType(IntEnum):
    BLE_LOCK = 1
    BLE_UNLOCK = 2
    AUTO_LOCK = 6
    MANUAL_LOCK = 7
    MANUAL_UNLOCKED = 8
    MANUAL_UNLOCKED_TO_LOCKED = 9
    WIFI_LOCK = 14
    WIFI_UNLOCK = 15
    WEB_LOCK = 16
    WEB_UNLOCK = 17


UNLOCK_HISTORY_TYPES = {
    HistoryType.BLE_UNLOCK,
    HistoryType.MANUAL_UNLOCKED,
    HistoryType.MANUAL_UNLOCKED_TO_LOCKED,
    HistoryType.WIFI_UNLOCK,
    HistoryType.WEB_UNLOCK,
}


@dataclass(frozen=True)
class HistoryRecord:
    payload: bytes

    def __post_init__(self) -> None:
        if len(self.payload) < 5:
            raise ValueError(
                "history payload must contain a 4-byte record id and event type"
            )

    @property
    def record_id(self) -> str:
        return self.payload[:4].hex()

    @property
    def payload_hex(self) -> str:
        return self.payload.hex()

    @property
    def event_type(self) -> int:
        return self.payload[4]

    @property
    def is_unlock(self) -> bool:
        return self.event_type in UNLOCK_HISTORY_TYPES

    def to_json_line(self, source: str = "sesame5") -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "record_id": self.record_id,
                "event_type": self.event_type,
                "is_unlock": self.is_unlock,
                "payload_hex": self.payload_hex,
                "payload_len": len(self.payload),
            },
            ensure_ascii=False,
        )


def is_touch_pro_history(payload: bytes, matcher: TouchProMatch) -> bool:
    # The first four bytes are a changing record ID. Match only the event body.
    event_hex = payload[4:].hex()
    if matcher.prefix_hex and not event_hex.startswith(matcher.prefix_hex):
        return False
    if matcher.contains_hex:
        return all(pattern in event_hex for pattern in matcher.contains_hex)
    return matcher.prefix_hex is not None
