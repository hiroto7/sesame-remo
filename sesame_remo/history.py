from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from .config import TouchProMatch


@dataclass(frozen=True)
class HistoryRecord:
    payload: bytes

    @property
    def record_id(self) -> str:
        return self.payload[:4].hex()

    @property
    def payload_hex(self) -> str:
        return self.payload.hex()

    def to_json_line(self, source: str = "sesame5") -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "record_id": self.record_id,
                "payload_hex": self.payload_hex,
                "payload_len": len(self.payload),
            },
            ensure_ascii=False,
        )


def is_touch_pro_history(payload: bytes, matcher: TouchProMatch) -> bool:
    payload_hex = payload.hex()
    if matcher.prefix_hex and not payload_hex.startswith(matcher.prefix_hex):
        return False
    if matcher.contains_hex:
        return all(pattern in payload_hex for pattern in matcher.contains_hex)
    return False

