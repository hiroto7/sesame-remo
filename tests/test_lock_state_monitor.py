from pathlib import Path

import pytest

from sesame_remo.config import Config
from sesame_remo.lock_state_monitor import run_lock_state_monitor
from sesame_remo.status import Sesame5MechanismStatus


def _config() -> Config:
    return Config(
        sesame_id="10000000-0000-0000-0000-000000000000",
        sesame_secret_key="00112233445566778899aabbccddeeff",
        nature_token="token",
        nature_light_appliance_id="appliance",
    )


@pytest.mark.asyncio
async def test_lock_state_monitor_rejects_missing_sound_before_monitoring(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="sound file not found"):
        await run_lock_state_monitor(
            _config(),
            scan_timeout=1,
            poll_interval=1,
            sound_path=str(tmp_path / "missing.aiff"),
            volume=0.25,
            repeat_gap=1,
        )


@pytest.mark.asyncio
async def test_unlock_transition_turns_light_on_once(
    monkeypatch, tmp_path: Path
) -> None:
    sound_path = tmp_path / "sound.aiff"
    sound_path.touch()
    statuses = [
        Sesame5MechanismStatus(bytes.fromhex("00000000341200")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341200")),
    ]
    light_calls: list[int] = []
    sound_started: list[int] = []
    sound_stopped: list[int] = []

    class FakeSound:
        def __init__(self, *_args, **_kwargs) -> None:
            self.sound_path = sound_path

        async def start(self) -> None:
            sound_started.append(1)

        async def stop(self) -> None:
            sound_stopped.append(1)

    class FakeRemo:
        def __init__(self, *_args) -> None:
            pass

        def send_light_on(self) -> None:
            light_calls.append(1)

    async def fake_run_monitor(_cfg, *, status_handler, **_kwargs) -> None:
        for status in statuses:
            await status_handler(status)

    monkeypatch.setattr("sesame_remo.lock_state_monitor.MacSoundLoop", FakeSound)
    monkeypatch.setattr("sesame_remo.lock_state_monitor.NatureRemoClient", FakeRemo)
    monkeypatch.setattr("sesame_remo.lock_state_monitor.run_monitor", fake_run_monitor)

    await run_lock_state_monitor(
        _config(),
        scan_timeout=1,
        poll_interval=1,
        sound_path=str(sound_path),
        volume=0.25,
        repeat_gap=1,
    )

    assert len(light_calls) == 1
    assert len(sound_started) == 2
    assert len(sound_stopped) == 3
