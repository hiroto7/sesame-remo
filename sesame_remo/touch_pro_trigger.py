from __future__ import annotations

from dataclasses import dataclass, field
import time


@dataclass
class EventGate:
    cooldown_seconds: int
    seen_record_ids: set[str] = field(default_factory=set)
    _last_sent_at: float | None = None

    def can_send(self, record_id: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        if record_id in self.seen_record_ids:
            return False
        if (
            self._last_sent_at is not None
            and current - self._last_sent_at < self.cooldown_seconds
        ):
            return False
        return True

    def mark_sent(self, record_id: str, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        self.seen_record_ids.add(record_id)
        self._last_sent_at = current
