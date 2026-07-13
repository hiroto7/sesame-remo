from __future__ import annotations

import argparse
import asyncio
import sys

from .config import load_config
from .daemon import EventGate
from .history import HistoryRecord, is_touch_pro_history
from .key_qr import decode_sesame5_share_url
from .nature import NatureRemoClient
from .sesame_client import SesameOS3Client, SesameScanTimeout


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


async def daemon(config_path: str, scan_timeout: float, poll_interval: float) -> int:
    cfg = load_config(config_path)
    gate = EventGate(cfg.cooldown_seconds)
    remo = NatureRemoClient(cfg.nature_token, cfg.nature_light_on_signal_id)
    if not cfg.touch_pro_match.contains_hex and not cfg.touch_pro_match.prefix_hex:
        raise ValueError("touch_pro_match must be configured before starting daemon")
    if not cfg.delete_history_after_read:
        raise ValueError(
            "daemon requires delete_history_after_read=true to advance the history queue"
        )
    if not cfg.nature_token or cfg.nature_token == "replace-me":
        raise ValueError("nature_token must be configured before starting daemon")
    if (
        not cfg.nature_light_on_signal_id
        or cfg.nature_light_on_signal_id == "replace-me"
    ):
        raise ValueError(
            "nature_light_on_signal_id must be configured before starting daemon"
        )

    while True:
        try:
            client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)

            async def handle(record: HistoryRecord) -> None:
                print(record.to_json_line(), flush=True)
                if not record.is_unlock:
                    return
                if not is_touch_pro_history(record.payload, cfg.touch_pro_match):
                    return
                if not gate.can_send(record.record_id):
                    return
                await asyncio.to_thread(remo.send_light_on)
                gate.mark_sent(record.record_id)
                print(
                    f"sent Nature Remo signal for record {record.record_id}", flush=True
                )

            await client.consume_history_once(
                handle,
                scan_timeout=scan_timeout,
                delete_after_success=True,
            )
        except SesameScanTimeout:
            pass
        except Exception as exc:
            print(f"daemon error: {exc}", file=sys.stderr, flush=True)
        await asyncio.sleep(poll_interval)


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

    dump = sub.add_parser("history-dump")
    dump.add_argument("--config", required=True)
    dump.add_argument("--scan-timeout", type=float, default=10.0)
    dump.add_argument(
        "--delete-after-read", action=argparse.BooleanOptionalAction, default=None
    )

    run = sub.add_parser("daemon")
    run.add_argument("--config", required=True)
    run.add_argument("--scan-timeout", type=float, default=10.0)
    run.add_argument("--poll-interval", type=float, default=2.0)

    sub.add_parser("decode-qr")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "history-dump":
            return asyncio.run(
                history_dump(args.config, args.scan_timeout, args.delete_after_read)
            )
        if args.command == "daemon":
            return asyncio.run(
                daemon(args.config, args.scan_timeout, args.poll_interval)
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
