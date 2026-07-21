from __future__ import annotations

import argparse
import asyncio
import sys

from .automation import SesameRemoActions, load_config
from .automation.sound import DEFAULT_REPEAT_GAP, DEFAULT_SOUND_PATH, DEFAULT_VOLUME
from .core import load_sesame_config, run_lock_monitor
from .core.key_qr import decode_sesame5_share_url
from .core.sesame_client import SesameOS3Client
from .macos_service import (
    DEFAULT_SERVICE_LABEL,
    install_service,
    service_status,
    service_target,
    uninstall_service,
)


async def monitor(
    config_path: str,
    scan_timeout: float,
    poll_interval: float,
    sound_path: str,
    volume: float,
    repeat_gap: float,
) -> int:
    cfg = load_config(config_path)
    actions = SesameRemoActions(
        cfg,
        sound_path=sound_path,
        volume=volume,
        repeat_gap=repeat_gap,
    )
    try:
        await actions.prepare()
        await run_lock_monitor(
            cfg.sesame,
            scan_timeout=scan_timeout,
            poll_interval=poll_interval,
            on_locked=actions.on_locked,
            on_unlocked=actions.on_unlocked,
            on_status=actions.on_status,
            on_connection_lost=actions.on_connection_lost,
            connection_event_handler=actions.handle_connection_event,
            cycle_event_handler=actions.handle_cycle_event,
        )
    finally:
        await actions.close()
    return 0


async def status_dump(config_path: str, scan_timeout: float) -> int:
    cfg = load_sesame_config(config_path)
    client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)
    status = await client.read_status_once(scan_timeout=scan_timeout)
    print(status.to_json_line(), flush=True)
    return 0


def decode_qr() -> int:
    share_url = sys.stdin.read().strip()
    if not share_url:
        raise ValueError("pipe a Sesame owner/manager share URL to standard input")
    key = decode_sesame5_share_url(share_url)
    print(f'sesame_id = "{key.device_id}"')
    print(f'sesame_secret_key = "{key.secret_key.hex()}"')
    return 0


def install_macos_service(config_path: str, label: str) -> int:
    plist_path = install_service(config_path, label=label)
    print(f"installed: {service_target(label)}")
    print(f"plist: {plist_path}")
    return 0


def uninstall_macos_service(label: str) -> int:
    if uninstall_service(label=label):
        print(f"uninstalled: {service_target(label)}")
    else:
        print(f"not installed: {service_target(label)}")
    return 0


def show_macos_service_status(label: str) -> int:
    result = service_status(label=label)
    if result.returncode == 0:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        return 0
    print(f"not installed: {service_target(label)}")
    print(
        "install with: sesame-remo service install --config config.toml"
        + (f" --label {label}" if label != DEFAULT_SERVICE_LABEL else "")
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sesame-remo")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("monitor", help="Monitor lock state and control feedback")
    run.add_argument("--config", required=True)
    run.add_argument("--scan-timeout", type=float, default=10.0)
    run.add_argument("--poll-interval", type=float, default=2.0)
    run.add_argument("--sound", default=DEFAULT_SOUND_PATH)
    run.add_argument("--volume", type=float, default=DEFAULT_VOLUME)
    run.add_argument("--repeat-gap", type=float, default=DEFAULT_REPEAT_GAP)

    status = sub.add_parser("status-dump", help="Read the current lock state once")
    status.add_argument("--config", required=True)
    status.add_argument("--scan-timeout", type=float, default=10.0)

    sub.add_parser("decode-qr", help="Decode a Sesame owner/manager share URL")

    service = sub.add_parser("service", help="Manage the macOS LaunchAgent")
    service_sub = service.add_subparsers(dest="service_command", required=True)

    install = service_sub.add_parser("install", help="Install and start the service")
    install.add_argument("--config", required=True)
    install.add_argument("--label", default=DEFAULT_SERVICE_LABEL)

    uninstall = service_sub.add_parser("uninstall", help="Stop and remove the service")
    uninstall.add_argument("--label", default=DEFAULT_SERVICE_LABEL)

    service_status_parser = service_sub.add_parser(
        "status", help="Show the service status"
    )
    service_status_parser.add_argument("--label", default=DEFAULT_SERVICE_LABEL)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "monitor":
            return asyncio.run(
                monitor(
                    args.config,
                    args.scan_timeout,
                    args.poll_interval,
                    args.sound,
                    args.volume,
                    args.repeat_gap,
                )
            )
        if args.command == "status-dump":
            return asyncio.run(status_dump(args.config, args.scan_timeout))
        if args.command == "decode-qr":
            return decode_qr()
        if args.command == "service":
            if args.service_command == "install":
                return install_macos_service(args.config, args.label)
            if args.service_command == "uninstall":
                return uninstall_macos_service(args.label)
            if args.service_command == "status":
                return show_macos_service_status(args.label)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        detail = str(exc) or type(exc).__name__
        print(f"error: {detail}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
