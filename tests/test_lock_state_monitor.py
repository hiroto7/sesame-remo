from pathlib import Path
import asyncio
import threading

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


@pytest.mark.asyncio
async def test_nature_request_does_not_block_status_or_sound(
    monkeypatch, tmp_path: Path
) -> None:
    sound_path = tmp_path / "sound.aiff"
    sound_path.touch()
    request_started = threading.Event()
    release_request = threading.Event()
    request_finished = threading.Event()
    sound_started = False

    class FakeSound:
        def __init__(self, *_args, **_kwargs) -> None:
            self.sound_path = sound_path

        async def start(self) -> None:
            nonlocal sound_started
            sound_started = True

        async def stop(self) -> None:
            return None

    class FakeRemo:
        def __init__(self, *_args) -> None:
            pass

        def send_light_on(self) -> None:
            request_started.set()
            release_request.wait(timeout=5)
            request_finished.set()

    async def fake_run_monitor(_cfg, *, status_handler, **_kwargs) -> None:
        await status_handler(Sesame5MechanismStatus(bytes.fromhex("00000000341202")))
        await status_handler(Sesame5MechanismStatus(bytes.fromhex("00000000341200")))
        for _ in range(100):
            if request_started.is_set():
                break
            await asyncio.sleep(0.01)
        assert request_started.is_set()
        assert sound_started
        assert not request_finished.is_set()
        release_request.set()

    monkeypatch.setattr("sesame_remo.lock_state_monitor.MacSoundLoop", FakeSound)
    monkeypatch.setattr("sesame_remo.lock_state_monitor.NatureRemoClient", FakeRemo)
    monkeypatch.setattr("sesame_remo.lock_state_monitor.run_monitor", fake_run_monitor)

    try:
        await run_lock_state_monitor(
            _config(),
            scan_timeout=1,
            poll_interval=1,
            sound_path=str(sound_path),
            volume=0.25,
            repeat_gap=1,
        )
    finally:
        release_request.set()

    assert request_finished.is_set()
