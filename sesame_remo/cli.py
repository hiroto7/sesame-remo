from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import sys
import time

from .config import load_config
from .touch_pro_trigger import EventGate, make_touch_pro_history_handler
from .history import HistoryRecord
from .key_qr import decode_sesame5_share_url
from .nature import NatureRemoClient
from .sesame_client import SesameOS3Client, SesameScanTimeout
from .sound import DEFAULT_REPEAT_GAP, DEFAULT_SOUND_PATH, DEFAULT_VOLUME
from .lock_state_monitor import run_lock_state_monitor
from .status import Sesame5MechanismStatus


async def history_dump(
    config_path: str, scan_timeout: float, delete_after_read: bool | None
) -> int:
    cfg = load_config(config_path)
    client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)
    should_delete = (
        cfg.delete_history_after_read
        if delete_after_read is None
        else delete_after_read
    )

    async def print_record(record: HistoryRecord) -> None:
        print(record.to_json_line(), flush=True)

    record = await client.consume_history_once(
        print_record,
        scan_timeout=scan_timeout,
        delete_after_success=should_delete,
    )
    if should_delete:
        print(f"deleted history record {record.record_id}", file=sys.stderr, flush=True)
    return 0


async def status_dump(config_path: str, scan_timeout: float) -> int:
    cfg = load_config(config_path)
    client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)
    status = await client.read_status_once(scan_timeout=scan_timeout)
    print(status.to_json_line(), flush=True)
    return 0


async def lock_state_monitor(
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


async def combined_monitor(
    config_path: str,
    scan_timeout: float,
    poll_interval: float,
    sound_path: str,
    volume: float,
    repeat_gap: float,
) -> int:
    cfg = load_config(config_path)
    _validate_touch_pro_config(cfg, "combined-monitor")
    gate = EventGate(cfg.cooldown_seconds)
    remo = NatureRemoClient(
        cfg.nature_token,
        cfg.nature_light_appliance_id,
        cfg.nature_light_button,
    )
    last_unlock_transition_at: float | None = None
    last_locked: bool | None = None

    async def log_event(event: str, fields: dict[str, object] | None = None) -> None:
        print(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": event,
                    **(fields or {}),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    async def handle_status(status: Sesame5MechanismStatus) -> None:
        nonlocal last_unlock_transition_at
        nonlocal last_locked
        if last_locked is not None and last_locked and not status.is_locked:
            last_unlock_transition_at = time.monotonic()
        last_locked = status.is_locked

    handle_history = make_touch_pro_history_handler(
        cfg,
        remo,
        gate,
        log_event,
        lambda: last_unlock_transition_at,
    )
    return await run_lock_state_monitor(
        cfg,
        scan_timeout=scan_timeout,
        poll_interval=poll_interval,
        sound_path=sound_path,
        volume=volume,
        repeat_gap=repeat_gap,
        history_handler=handle_history,
        history_event_handler=log_event,
        status_event_handler=handle_status,
    )


async def touch_pro_trigger(
    config_path: str, scan_timeout: float, poll_interval: float
) -> int:
    cfg = load_config(config_path)
    gate = EventGate(cfg.cooldown_seconds)
    remo = NatureRemoClient(
        cfg.nature_token,
        cfg.nature_light_appliance_id,
        cfg.nature_light_button,
    )
    _validate_touch_pro_config(cfg, "touch-pro-trigger")

    cycle = 0
    last_locked: bool | None = None
    last_unlock_transition_at: float | None = None
    while True:
        cycle += 1
        cycle_started_at = time.monotonic()

        async def log_event(
            event: str, fields: dict[str, object] | None = None
        ) -> None:
            print(
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": event,
                        "cycle": cycle,
                        "elapsed_seconds": time.monotonic() - cycle_started_at,
                        **(fields or {}),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        async def handle_status(status: Sesame5MechanismStatus) -> None:
            nonlocal last_locked
            nonlocal last_unlock_transition_at
            fields = status.to_json_dict()
            fields["source"] = "mechStatus"
            await log_event("status_received", fields)
            if last_locked is not None and last_locked != status.is_locked:
                if not status.is_locked:
                    last_unlock_transition_at = time.monotonic()
                await log_event(
                    "status_state_changed",
                    {
                        "from_locked": last_locked,
                        "to_locked": status.is_locked,
                    },
                )
            last_locked = status.is_locked

        try:
            await log_event("cycle_started")
            client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)

            handle = make_touch_pro_history_handler(
                cfg,
                remo,
                gate,
                log_event,
                lambda: last_unlock_transition_at,
            )

            await client.monitor_status(
                handle_status,
                scan_timeout=scan_timeout,
                history_handler=handle,
                history_event_handler=log_event,
            )
        except SesameScanTimeout as exc:
            await log_event("cycle_timeout", {"error": str(exc)})
        except Exception as exc:
            await log_event("cycle_failed", {"error": str(exc)})
            print(f"touch-pro-trigger error: {exc}", file=sys.stderr, flush=True)
        finally:
            await log_event("cycle_finished")
        await asyncio.sleep(poll_interval)


def _validate_touch_pro_config(cfg, command: str) -> None:
    if not cfg.touch_pro_match.contains_hex and not cfg.touch_pro_match.prefix_hex:
        raise ValueError(
            f"touch_pro_match must be configured before starting {command}"
        )
    if not cfg.delete_history_after_read:
        raise ValueError(
            f"{command} requires delete_history_after_read=true "
            "to advance the history queue"
        )
    if not cfg.nature_token or cfg.nature_token == "replace-me":
        raise ValueError(f"nature_token must be configured before starting {command}")
    if (
        not cfg.nature_light_appliance_id
        or cfg.nature_light_appliance_id == "replace-me"
    ):
        raise ValueError(
            f"nature_light_appliance_id must be configured before starting {command}"
        )
    if not cfg.nature_light_button:
        raise ValueError("nature_light_button must not be empty")


def decode_qr() -> int:
    share_url = sys.stdin.read().strip()
    if not share_url:
        raise ValueError("pipe a Sesame owner/manager share URL to standard input")
    key = decode_sesame5_share_url(share_url)
    print(f'sesame_id = "{key.device_id}"')
    print(f'sesame_secret_key = "{key.secret_key.hex()}"')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sesame-remo")
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser(
        "history-dump", help="Read one Sesame history record and optionally delete it"
    )
    dump.add_argument("--config", required=True)
    dump.add_argument("--scan-timeout", type=float, default=10.0)
    dump.add_argument(
        "--delete-after-read", action=argparse.BooleanOptionalAction, default=None
    )

    status = sub.add_parser("status-dump", help="Read the current lock state once")
    status.add_argument("--config", required=True)
    status.add_argument("--scan-timeout", type=float, default=10.0)

    status_run = sub.add_parser(
        "lock-state-monitor",
        help="Monitor lock state and play sound while unlocked",
    )
    status_run.add_argument("--config", required=True)
    status_run.add_argument("--scan-timeout", type=float, default=10.0)
    status_run.add_argument("--poll-interval", type=float, default=2.0)
    status_run.add_argument("--sound", default=DEFAULT_SOUND_PATH)
    status_run.add_argument("--volume", type=float, default=DEFAULT_VOLUME)
    status_run.add_argument("--repeat-gap", type=float, default=DEFAULT_REPEAT_GAP)

    run = sub.add_parser(
        "touch-pro-trigger",
        help="Trigger Nature Remo for Touch Pro unlock history",
    )
    run.add_argument("--config", required=True)
    run.add_argument("--scan-timeout", type=float, default=10.0)
    run.add_argument("--poll-interval", type=float, default=2.0)

    combined = sub.add_parser(
        "combined-monitor",
        help="Play sound for unlocks and trigger Nature Remo for Touch Pro unlocks",
    )
    combined.add_argument("--config", required=True)
    combined.add_argument("--scan-timeout", type=float, default=10.0)
    combined.add_argument("--poll-interval", type=float, default=2.0)
    combined.add_argument("--sound", default=DEFAULT_SOUND_PATH)
    combined.add_argument("--volume", type=float, default=DEFAULT_VOLUME)
    combined.add_argument("--repeat-gap", type=float, default=DEFAULT_REPEAT_GAP)

    sub.add_parser("decode-qr", help="Decode a Sesame owner/manager share URL")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "history-dump":
            return asyncio.run(
                history_dump(args.config, args.scan_timeout, args.delete_after_read)
            )
        if args.command == "status-dump":
            return asyncio.run(status_dump(args.config, args.scan_timeout))
        if args.command == "lock-state-monitor":
            return asyncio.run(
                lock_state_monitor(
                    args.config,
                    args.scan_timeout,
                    args.poll_interval,
                    args.sound,
                    args.volume,
                    args.repeat_gap,
                )
            )
        if args.command == "touch-pro-trigger":
            return asyncio.run(
                touch_pro_trigger(args.config, args.scan_timeout, args.poll_interval)
            )
        if args.command == "combined-monitor":
            return asyncio.run(
                combined_monitor(
                    args.config,
                    args.scan_timeout,
                    args.poll_interval,
                    args.sound,
                    args.volume,
                    args.repeat_gap,
                )
            )
        if args.command == "decode-qr":
            return decode_qr()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        detail = str(exc) or type(exc).__name__
        print(f"error: {detail}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
