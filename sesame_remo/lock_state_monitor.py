from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from collections.abc import Callable
from functools import partial
import json
import sys

from .config import Config
from .monitor_runner import (
    run_monitor,
)
from .nature import NatureRemoClient
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
) -> int:
    sound = MacSoundLoop(
        sound_path,
        volume=volume,
        repeat_gap=repeat_gap,
    )
    if not sound.sound_path.is_file():
        raise FileNotFoundError(f"sound file not found: {sound.sound_path}")
    last_locked: bool | None = None
    nature_tasks: set[asyncio.Task[None]] = set()
    remo = NatureRemoClient(cfg.nature_token)

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
            print(f"sesame-remo error: {error}", file=sys.stderr, flush=True)

    async def handle_connection_event(event: str) -> None:
        log_event(event)

    async def send_nature_request(
        request_type: str,
        target_id: str,
        operation: Callable[[], None],
        *,
        button: str | None = None,
    ) -> None:
        try:
            await asyncio.to_thread(operation)
        except Exception as exc:
            log_event(
                "nature_request_completed",
                request_type=request_type,
                target_id=target_id,
                button=button,
                success=False,
                error=str(exc),
            )
        else:
            log_event(
                "nature_request_completed",
                request_type=request_type,
                target_id=target_id,
                button=button,
                success=True,
            )

    def schedule_nature_request(
        request_type: str,
        target_id: str,
        operation: Callable[[], None],
        *,
        button: str | None = None,
    ) -> None:
        log_event(
            "nature_request_started",
            request_type=request_type,
            target_id=target_id,
            button=button,
        )
        task = asyncio.create_task(
            send_nature_request(
                request_type,
                target_id,
                operation,
                button=button,
            )
        )
        nature_tasks.add(task)
        task.add_done_callback(nature_tasks.discard)

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
        if last_locked is True and status.is_unlocked:
            schedule_nature_request(
                "light_button",
                cfg.nature_light_appliance_id,
                partial(
                    remo.send_light_button,
                    cfg.nature_light_appliance_id,
                    cfg.nature_light_button,
                ),
                button=cfg.nature_light_button,
            )
            for signal_id in cfg.nature_unlock_signal_ids:
                schedule_nature_request(
                    "signal",
                    signal_id,
                    partial(remo.send_signal, signal_id),
                )
        elif last_locked is False and status.is_locked:
            for signal_id in cfg.nature_lock_signal_ids:
                schedule_nature_request(
                    "signal",
                    signal_id,
                    partial(remo.send_signal, signal_id),
                )
        last_locked = status.is_locked
        if status.is_unlocked:
            await sound.start()
        else:
            await sound.stop()

    try:
        await run_monitor(
            cfg,
            scan_timeout=scan_timeout,
            poll_interval=poll_interval,
            status_handler=handle_status,
            connection_lost_handler=sound.stop,
            connection_event_handler=handle_connection_event,
            cycle_event_handler=handle_cycle_event,
        )
    finally:
        await sound.stop()
        if nature_tasks:
            await asyncio.gather(*nature_tasks, return_exceptions=True)
    return 0
