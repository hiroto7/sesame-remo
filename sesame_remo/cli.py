from __future__ import annotations

import argparse
import asyncio
import sys
import time

from .config import load_config
from .daemon import EventGate
from .history import is_touch_pro_history
from .nature import NatureRemoClient
from .sesame_client import SesameOS3Client


async def history_dump(config_path: str, scan_timeout: float, delete_after_read: bool | None) -> int:
    cfg = load_config(config_path)
    client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)
    should_delete = cfg.delete_history_after_read if delete_after_read is None else delete_after_read
    record = await client.read_history_once(scan_timeout=scan_timeout, delete_after_read=should_delete)
    print(record.to_json_line(), flush=True)
    if should_delete:
        print(f"deleted history record {record.record_id}", file=sys.stderr, flush=True)
    return 0


async def daemon(config_path: str, scan_timeout: float, poll_interval: float) -> int:
    cfg = load_config(config_path)
    gate = EventGate(cfg.cooldown_seconds)
    remo = NatureRemoClient(cfg.nature_token, cfg.nature_light_on_signal_id)
    if not cfg.touch_pro_match.contains_hex and not cfg.touch_pro_match.prefix_hex:
        print("touch_pro_match is not configured; daemon will not send Nature Remo signals", file=sys.stderr)
    if not cfg.delete_history_after_read:
        print("delete_history_after_read=false; repeated old records may block later history reads", file=sys.stderr)

    while True:
        try:
            client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)
            record = await client.read_history_once(
                scan_timeout=scan_timeout,
                delete_after_read=cfg.delete_history_after_read,
            )
            print(record.to_json_line(), flush=True)
            if is_touch_pro_history(record.payload, cfg.touch_pro_match) and gate.should_send(record.record_id):
                remo.send_light_on()
                print(f"sent Nature Remo signal for record {record.record_id}", flush=True)
        except TimeoutError:
            pass
        except Exception as exc:
            print(f"daemon error: {exc}", file=sys.stderr, flush=True)
        await asyncio.sleep(poll_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sesame-remo")
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser("history-dump")
    dump.add_argument("--config", required=True)
    dump.add_argument("--scan-timeout", type=float, default=10.0)
    dump.add_argument("--delete-after-read", action="store_true", default=None)

    run = sub.add_parser("daemon")
    run.add_argument("--config", required=True)
    run.add_argument("--scan-timeout", type=float, default=10.0)
    run.add_argument("--poll-interval", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start = time.monotonic()
    try:
        if args.command == "history-dump":
            return asyncio.run(history_dump(args.config, args.scan_timeout, args.delete_after_read))
        if args.command == "daemon":
            return asyncio.run(daemon(args.config, args.scan_timeout, args.poll_interval))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        _ = start
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
