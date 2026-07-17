from __future__ import annotations

import argparse
import asyncio
import sys

from .config import load_config
from .lock_state_monitor import run_lock_state_monitor
from .sound import DEFAULT_REPEAT_GAP, DEFAULT_SOUND_PATH, DEFAULT_VOLUME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sesame-remo")
    parser.add_argument("--config", required=True)
    parser.add_argument("--scan-timeout", type=float, default=10.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--sound", default=DEFAULT_SOUND_PATH)
    parser.add_argument("--volume", type=float, default=DEFAULT_VOLUME)
    parser.add_argument("--repeat-gap", type=float, default=DEFAULT_REPEAT_GAP)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(
            _run(
                args.config,
                args.scan_timeout,
                args.poll_interval,
                args.sound,
                args.volume,
                args.repeat_gap,
            )
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        detail = str(exc) or type(exc).__name__
        print(f"error: {detail}", file=sys.stderr)
        return 1


async def _run(
    config_path: str,
    scan_timeout: float,
    poll_interval: float,
    sound_path: str,
    volume: float,
    repeat_gap: float,
) -> int:
    cfg = load_config(config_path)
    return await run_lock_state_monitor(
        cfg,
        scan_timeout=scan_timeout,
        poll_interval=poll_interval,
        sound_path=sound_path,
        volume=volume,
        repeat_gap=repeat_gap,
    )


if __name__ == "__main__":
    raise SystemExit(main())
