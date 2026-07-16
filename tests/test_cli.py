from sesame_remo.cli import build_parser


def test_lock_state_monitor_parser_defaults() -> None:
    args = build_parser().parse_args(["lock-state-monitor", "--config", "config.toml"])

    assert args.command == "lock-state-monitor"
    assert args.volume == 0.25
    assert args.repeat_gap == 1.0
