from pathlib import Path
import asyncio
import threading

import pytest

from sesame_remo.automation.actions import SesameRemoActions
from sesame_remo.automation.config import AppConfig
from sesame_remo.core.config import SesameConfig
from sesame_remo.core.monitor import LockStateEvent
from sesame_remo.core.status import Sesame5MechanismStatus


def _config() -> AppConfig:
    return AppConfig(
        sesame=SesameConfig(
            sesame_id="10000000-0000-0000-0000-000000000000",
            sesame_secret_key="00112233445566778899aabbccddeeff",
        ),
        nature_token="token",
        nature_light_appliance_id="appliance",
        nature_unlock_signal_ids=("on-signal", "fade-signal"),
        nature_lock_signal_ids=("on-signal", "white-signal"),
    )


def test_actions_reject_missing_sound_before_monitoring(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="sound file not found"):
        SesameRemoActions(
            _config(),
            sound_path=str(tmp_path / "missing.aiff"),
            volume=0.25,
            repeat_gap=1,
        )


@pytest.mark.asyncio
async def test_lock_transitions_send_configured_nature_actions_once(
    monkeypatch, tmp_path: Path
) -> None:
    sound_path = tmp_path / "sound.aiff"
    sound_path.touch()
    statuses = [
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341200")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341200")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
    ]
    light_calls: list[tuple[str, str]] = []
    signal_calls: list[str] = []
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

        def send_light_button(self, appliance_id: str, button: str) -> None:
            light_calls.append((appliance_id, button))

        def send_signal(self, signal_id: str) -> None:
            signal_calls.append(signal_id)

    monkeypatch.setattr("sesame_remo.automation.actions.MacSoundLoop", FakeSound)
    monkeypatch.setattr("sesame_remo.automation.actions.NatureRemoClient", FakeRemo)

    actions = SesameRemoActions(
        _config(),
        sound_path=str(sound_path),
        volume=0.25,
        repeat_gap=1,
    )
    previous = None
    for status in statuses:
        event = LockStateEvent(status=status, previous_status=previous)
        await actions.on_status(event)
        if event.changed:
            if status.is_locked:
                await actions.on_locked(event)
            else:
                await actions.on_unlocked(event)
        previous = status
    await actions.close()

    assert light_calls == [("appliance", "on")]
    assert sorted(signal_calls) == [
        "fade-signal",
        "on-signal",
        "on-signal",
        "white-signal",
    ]
    assert len(sound_started) == 2
    assert len(sound_stopped) == 4


@pytest.mark.asyncio
async def test_nature_request_does_not_block_sound(monkeypatch, tmp_path: Path) -> None:
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

        def send_light_button(self, _appliance_id: str, _button: str) -> None:
            request_started.set()
            release_request.wait(timeout=5)
            request_finished.set()

        def send_signal(self, _signal_id: str) -> None:
            return None

    monkeypatch.setattr("sesame_remo.automation.actions.MacSoundLoop", FakeSound)
    monkeypatch.setattr("sesame_remo.automation.actions.NatureRemoClient", FakeRemo)

    actions = SesameRemoActions(
        _config(),
        sound_path=str(sound_path),
        volume=0.25,
        repeat_gap=1,
    )
    locked = Sesame5MechanismStatus(bytes.fromhex("00000000341202"))
    unlocked = Sesame5MechanismStatus(bytes.fromhex("00000000341200"))
    await actions.on_status(LockStateEvent(locked, None))
    event = LockStateEvent(unlocked, locked)
    await actions.on_status(event)
    await actions.on_unlocked(event)

    try:
        for _ in range(100):
            if request_started.is_set():
                break
            await asyncio.sleep(0.01)
        assert request_started.is_set()
        assert sound_started
        assert not request_finished.is_set()
    finally:
        release_request.set()
        await actions.close()

    assert request_finished.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transition", "expected"),
    [
        ("unlocked", ["on-signal", "fade-signal"]),
        ("locked", ["on-signal", "white-signal"]),
    ],
)
async def test_transition_signals_are_sent_in_configured_order(
    monkeypatch, tmp_path: Path, transition: str, expected: list[str]
) -> None:
    sound_path = tmp_path / "sound.aiff"
    sound_path.touch()
    signal_calls: list[str] = []

    class FakeSound:
        def __init__(self, *_args, **_kwargs) -> None:
            self.sound_path = sound_path

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    class FakeRemo:
        def __init__(self, *_args) -> None:
            pass

        def send_light_button(self, _appliance_id: str, _button: str) -> None:
            return None

        def send_signal(self, signal_id: str) -> None:
            signal_calls.append(signal_id)

    monkeypatch.setattr("sesame_remo.automation.actions.MacSoundLoop", FakeSound)
    monkeypatch.setattr("sesame_remo.automation.actions.NatureRemoClient", FakeRemo)

    actions = SesameRemoActions(
        _config(),
        sound_path=str(sound_path),
        volume=0.25,
        repeat_gap=1,
    )
    locked = Sesame5MechanismStatus(bytes.fromhex("00000000341202"))
    unlocked = Sesame5MechanismStatus(bytes.fromhex("00000000341200"))
    if transition == "unlocked":
        await actions.on_unlocked(LockStateEvent(unlocked, locked))
    else:
        await actions.on_locked(LockStateEvent(locked, unlocked))
    await actions.close()

    assert signal_calls == expected
