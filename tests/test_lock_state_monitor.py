from pathlib import Path

import pytest

from sesame_remo.config import Config
from sesame_remo.lock_state_monitor import run_lock_state_monitor


@pytest.mark.asyncio
async def test_lock_state_monitor_rejects_missing_sound_before_monitoring(
    tmp_path: Path,
) -> None:
    config = Config(
        sesame_id="10000000-0000-0000-0000-000000000000",
        sesame_secret_key="00112233445566778899aabbccddeeff",
    )

    with pytest.raises(FileNotFoundError, match="sound file not found"):
        await run_lock_state_monitor(
            config,
            scan_timeout=1,
            poll_interval=1,
            sound_path=str(tmp_path / "missing.aiff"),
            volume=0.25,
            repeat_gap=1,
        )
