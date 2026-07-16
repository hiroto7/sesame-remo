from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import sys

from .config import Config
from .sesame_client import SesameOS3Client, SesameScanTimeout
from .sound import MacSoundLoop


async def run_lock_state_monitor(
    cfg: Config,
    *,
    scan_timeout: float,
    poll_interval: float,
    sound_path: str,
    volume: float,
    repeat_gap: float,
) -> int:
    if poll_interval < 0.0:
        raise ValueError("poll_interval must not be negative")

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

    async def handle_connection_event(event: str) -> None:
        log_event(event)

    try:
        while True:
            try:
                client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)

                async def handle_status(status) -> None:
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

                await client.monitor_status(
                    handle_status,
                    scan_timeout=scan_timeout,
                    connection_lost_handler=sound.stop,
                    connection_event_handler=handle_connection_event,
                )
            except SesameScanTimeout:
                await sound.stop()
                log_event("monitor_timeout")
            except Exception as exc:
                await sound.stop()
                log_event("monitor_error", error=str(exc))
                print(f"lock-state-monitor error: {exc}", file=sys.stderr, flush=True)
            await asyncio.sleep(poll_interval)
    finally:
        await sound.stop()
