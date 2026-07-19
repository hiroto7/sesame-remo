from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path


DEFAULT_SOUND_PATH = "/System/Library/Sounds/Ping.aiff"
DEFAULT_VOLUME = 0.25
DEFAULT_REPEAT_GAP = 1.0
PROCESS_TERMINATE_TIMEOUT = 5.0


class MacSoundLoop:
    def __init__(
        self,
        sound_path: str = DEFAULT_SOUND_PATH,
        *,
        volume: float = DEFAULT_VOLUME,
        repeat_gap: float = DEFAULT_REPEAT_GAP,
    ) -> None:
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between 0 and 1")
        if repeat_gap < 0.0:
            raise ValueError("repeat_gap must not be negative")
        if not sound_path:
            raise ValueError("sound_path must not be empty")
        self.sound_path = Path(sound_path)
        self.volume = volume
        self.repeat_gap = repeat_gap
        self._task: asyncio.Task[None] | None = None
        self._process: asyncio.subprocess.Process | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        if not self.sound_path.is_file():
            raise FileNotFoundError(f"sound file not found: {self.sound_path}")
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._task = None
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        try:
            while True:
                process = await asyncio.create_subprocess_exec(
                    "/usr/bin/afplay",
                    "-v",
                    str(self.volume),
                    str(self.sound_path),
                )
                self._process = process
                try:
                    await process.wait()
                finally:
                    try:
                        if process.returncode is None:
                            process.terminate()
                            with suppress(ProcessLookupError):
                                try:
                                    await asyncio.wait_for(
                                        process.wait(),
                                        timeout=PROCESS_TERMINATE_TIMEOUT,
                                    )
                                except TimeoutError:
                                    process.kill()
                                    await process.wait()
                    finally:
                        if self._process is process:
                            self._process = None
                await asyncio.sleep(self.repeat_gap)
        except asyncio.CancelledError:
            raise
