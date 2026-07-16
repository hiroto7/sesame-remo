from __future__ import annotations

import asyncio
import sys

from .config import Config
from .sesame_client import SesameOS3Client, SesameScanTimeout
from .sound import MacSoundLoop


async def run_status_daemon(
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
    try:
        while True:
            try:
                client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)

                async def handle_status(status) -> None:
                    print(status.to_json_line(), flush=True)
                    if status.is_unlocked:
                        await sound.start()
                    else:
                        await sound.stop()

                await client.monitor_status(
                    handle_status,
                    scan_timeout=scan_timeout,
                )
            except SesameScanTimeout:
                await sound.stop()
            except Exception as exc:
                await sound.stop()
                print(f"status daemon error: {exc}", file=sys.stderr, flush=True)
            await asyncio.sleep(poll_interval)
    finally:
        await sound.stop()
