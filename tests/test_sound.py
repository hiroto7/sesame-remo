import pytest

from sesame_remo.sound import MacSoundLoop


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
