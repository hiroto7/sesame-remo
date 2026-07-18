import pytest

from sesame_remo.cli import build_parser, status_dump
from sesame_remo.config import Config
from sesame_remo.status import Sesame5MechanismStatus


def test_monitor_parser_defaults() -> None:
    args = build_parser().parse_args(["monitor", "--config", "config.toml"])

    assert args.command == "monitor"
    assert args.config == "config.toml"
    assert args.poll_interval == 2.0
    assert args.volume == 0.25
    assert args.repeat_gap == 1.0


def test_status_dump_parser_defaults() -> None:
    args = build_parser().parse_args(["status-dump", "--config", "config.toml"])

    assert args.command == "status-dump"
    assert args.scan_timeout == 10.0


def test_decode_qr_parser() -> None:
    args = build_parser().parse_args(["decode-qr"])

    assert args.command == "decode-qr"


@pytest.mark.asyncio
async def test_status_dump_reads_once(monkeypatch, capsys) -> None:
    config = Config(
        sesame_id="10000000-0000-0000-0000-000000000000",
        sesame_secret_key="00112233445566778899aabbccddeeff",
        nature_token="token",
        nature_light_appliance_id="appliance",
    )

    class FakeClient:
        def __init__(self, sesame_id: str, secret_key: str) -> None:
            assert sesame_id == config.sesame_id
            assert secret_key == config.sesame_secret_key

        async def read_status_once(self, *, scan_timeout: float):
            assert scan_timeout == 3
            return Sesame5MechanismStatus(bytes.fromhex("00000000341202"))

    def fake_load_config(_path: str, *, require_nature: bool = True) -> Config:
        assert not require_nature
        return config

    monkeypatch.setattr("sesame_remo.cli.load_config", fake_load_config)
    monkeypatch.setattr("sesame_remo.cli.SesameOS3Client", FakeClient)

    assert await status_dump("config.toml", 3) == 0
    assert '"is_locked": true' in capsys.readouterr().out
