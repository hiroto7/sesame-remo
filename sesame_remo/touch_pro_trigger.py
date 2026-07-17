from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import time
from collections.abc import Awaitable, Callable

from .config import Config
from .history import HistoryRecord, is_touch_pro_history
from .nature import NatureRemoClient


EventLogger = Callable[[str, dict[str, object] | None], Awaitable[None]]


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


def make_touch_pro_history_handler(
    cfg: Config,
    remo: NatureRemoClient,
    gate: EventGate,
    log_event: EventLogger,
    get_last_unlock_transition_at: Callable[[], float | None],
) -> Callable[[HistoryRecord], Awaitable[None]]:
    async def handle(record: HistoryRecord) -> None:
        print(record.to_json_line(), flush=True)
        if not record.is_unlock:
            return
        matched = is_touch_pro_history(record.payload, cfg.touch_pro_match)
        await log_event(
            "touch_pro_evaluated",
            {"record_id": record.record_id, "matched": matched},
        )
        if not matched or not gate.can_send(record.record_id):
            return
        unlock_transition_at = get_last_unlock_transition_at()
        await log_event(
            "touch_pro_matched",
            {
                "record_id": record.record_id,
                "status_to_history_seconds": (
                    None
                    if unlock_transition_at is None
                    else time.monotonic() - unlock_transition_at
                ),
            },
        )
        await log_event("nature_request_started", {"record_id": record.record_id})
        try:
            await asyncio.to_thread(remo.send_light_on)
        except Exception as exc:
            await log_event(
                "nature_request_completed",
                {
                    "record_id": record.record_id,
                    "success": False,
                    "error": str(exc),
                },
            )
            return
        await log_event(
            "nature_request_completed",
            {"record_id": record.record_id, "success": True},
        )
        gate.mark_sent(record.record_id)
        print(
            f"turned on Nature Remo light for record {record.record_id}",
            flush=True,
        )

    return handle
