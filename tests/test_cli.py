from sesame_remo.cli import build_parser


def test_status_daemon_parser_defaults() -> None:
    args = build_parser().parse_args(["status-daemon", "--config", "config.toml"])

    assert args.command == "status-daemon"
    assert args.volume == 0.25
    assert args.repeat_gap == 1.0
