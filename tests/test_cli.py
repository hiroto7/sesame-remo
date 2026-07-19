import pytest

from sesame_remo.automation.config import AppConfig
from sesame_remo.cli import build_parser, monitor, status_dump
from sesame_remo.core.config import SesameConfig
from sesame_remo.core.status import Sesame5MechanismStatus


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
async def test_monitor_composes_core_with_automation(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        sesame=SesameConfig(
            sesame_id="10000000-0000-0000-0000-000000000000",
            sesame_secret_key="00112233445566778899aabbccddeeff",
        ),
        nature_token="token",
        nature_light_appliance_id="appliance",
    )
    closed = False

    class FakeActions:
        def __init__(self, received_config, **_kwargs) -> None:
            assert received_config is config

        async def on_locked(self, _event) -> None:
            return None

        async def on_unlocked(self, _event) -> None:
            return None

        async def on_status(self, _event) -> None:
            return None

        async def on_connection_lost(self) -> None:
            return None

        async def handle_connection_event(self, _event) -> None:
            return None

        async def handle_cycle_event(self, _event, _error) -> None:
            return None

        async def close(self) -> None:
            nonlocal closed
            closed = True

    async def fake_run_lock_monitor(received_config, **callbacks) -> None:
        assert received_config is config.sesame
        assert set(callbacks) == {
            "scan_timeout",
            "poll_interval",
            "on_locked",
            "on_unlocked",
            "on_status",
            "on_connection_lost",
            "connection_event_handler",
            "cycle_event_handler",
        }

    monkeypatch.setattr("sesame_remo.cli.load_config", lambda _path: config)
    monkeypatch.setattr("sesame_remo.cli.SesameRemoActions", FakeActions)
    monkeypatch.setattr("sesame_remo.cli.run_lock_monitor", fake_run_lock_monitor)

    assert await monitor("config.toml", 3, 2, str(tmp_path), 0.25, 1) == 0
    assert closed


@pytest.mark.asyncio
async def test_status_dump_reads_once(monkeypatch, capsys) -> None:
    config = SesameConfig(
        sesame_id="10000000-0000-0000-0000-000000000000",
        sesame_secret_key="00112233445566778899aabbccddeeff",
    )

    class FakeClient:
        def __init__(self, sesame_id: str, secret_key: str) -> None:
            assert sesame_id == config.sesame_id
            assert secret_key == config.sesame_secret_key

        async def read_status_once(self, *, scan_timeout: float):
            assert scan_timeout == 3
            return Sesame5MechanismStatus(bytes.fromhex("00000000341202"))

    def fake_load_config(_path: str) -> SesameConfig:
        return config

    monkeypatch.setattr("sesame_remo.cli.load_sesame_config", fake_load_config)
    monkeypatch.setattr("sesame_remo.cli.SesameOS3Client", FakeClient)

    assert await status_dump("config.toml", 3) == 0
    assert '"is_locked": true' in capsys.readouterr().out
