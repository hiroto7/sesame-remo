import asyncio

import pytest

from sesame_remo.automation.sound import MacSoundLoop


def test_sound_loop_defaults_to_stopped(tmp_path) -> None:
    sound = MacSoundLoop(str(tmp_path / "sound.aiff"))

    assert not sound.is_running


@pytest.mark.parametrize(
    "kwargs",
    [
        {"volume": -0.1},
        {"volume": 1.1},
        {"repeat_gap": -1.0},
    ],
)
def test_sound_loop_rejects_invalid_options(tmp_path, kwargs) -> None:
    with pytest.raises(ValueError):
        MacSoundLoop(str(tmp_path / "sound.aiff"), **kwargs)


@pytest.mark.asyncio
async def test_sound_loop_rejects_missing_sound_file(tmp_path) -> None:
    sound = MacSoundLoop(str(tmp_path / "missing.aiff"))

    with pytest.raises(FileNotFoundError):
        await sound.start()


@pytest.mark.asyncio
async def test_sound_loop_terminates_afplay_when_stopped(monkeypatch, tmp_path) -> None:
    started = asyncio.Event()
    finished = asyncio.Event()

    class FakeProcess:
        returncode = None
        terminated = False

        async def wait(self) -> None:
            await finished.wait()
            self.returncode = 0

        def terminate(self) -> None:
            self.terminated = True
            finished.set()

    process = FakeProcess()

    async def fake_create_subprocess_exec(*_args: str):
        started.set()
        return process

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    sound = MacSoundLoop(str(tmp_path / "sound.aiff"))
    sound.sound_path.touch()

    await sound.start()
    await started.wait()
    await sound.stop()

    assert process.terminated
