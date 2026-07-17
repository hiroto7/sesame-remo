import pytest

from sesame_remo.cli import build_parser


def test_parser_has_one_monitor_command() -> None:
    args = build_parser().parse_args(["--config", "config.toml"])

    assert args.config == "config.toml"
    assert args.poll_interval == 2.0
    assert args.volume == 0.25
    assert args.repeat_gap == 1.0


def test_parser_rejects_removed_subcommands() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["combined-monitor", "--config", "config.toml"])
