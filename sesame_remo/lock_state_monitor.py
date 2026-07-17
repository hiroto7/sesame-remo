from __future__ import annotations

from datetime import datetime, timezone
import json
import sys

from .config import Config
from .monitor_runner import (
    HistoryEventHandler,
    HistoryHandler,
    StatusHandler,
    run_monitor,
)
from .sound import MacSoundLoop
from .status import Sesame5MechanismStatus


async def run_lock_state_monitor(
    cfg: Config,
    *,
    scan_timeout: float,
    poll_interval: float,
    sound_path: str,
    volume: float,
    repeat_gap: float,
    history_handler: HistoryHandler | None = None,
    history_event_handler: HistoryEventHandler | None = None,
    status_event_handler: StatusHandler | None = None,
) -> int:
    sound = MacSoundLoop(
        sound_path,
        volume=volume,
        repeat_gap=repeat_gap,
    )
    if not sound.sound_path.is_file():
        raise FileNotFoundError(f"sound file not found: {sound.sound_path}")
    last_locked: bool | None = None

    def log_event(event: str, **fields: object) -> None:
        print(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": event,
                    **fields,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    async def handle_cycle_event(event: str, error: BaseException | None) -> None:
        if event == "cycle_timeout":
            log_event("monitor_timeout")
        elif event == "cycle_failed":
            assert error is not None
            log_event("monitor_error", error=str(error))
            print(f"lock-state-monitor error: {error}", file=sys.stderr, flush=True)

    async def handle_connection_event(event: str) -> None:
        log_event(event)

    async def handle_status(status: Sesame5MechanismStatus) -> None:
        nonlocal last_locked
        log_event("status", **status.to_json_dict())
        if last_locked is None or last_locked != status.is_locked:
            log_event(
                "state_changed",
                from_state=(
                    None
                    if last_locked is None
                    else ("locked" if last_locked else "unlocked")
                ),
                to_state="locked" if status.is_locked else "unlocked",
            )
        last_locked = status.is_locked
        if status.is_unlocked:
            await sound.start()
        else:
            await sound.stop()
        if status_event_handler is not None:
            await status_event_handler(status)

    try:
        await run_monitor(
            cfg,
            scan_timeout=scan_timeout,
            poll_interval=poll_interval,
            status_handler=handle_status,
            connection_lost_handler=sound.stop,
            connection_event_handler=handle_connection_event,
            history_handler=history_handler,
            history_event_handler=history_event_handler,
            cycle_event_handler=handle_cycle_event,
        )
    finally:
        await sound.stop()
    return 0
