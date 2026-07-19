from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
import json
import sys

from ..core.monitor import LockStateEvent
from .config import AppConfig
from .nature import NatureRemoClient
from .sound import MacSoundLoop


class SesameRemoActions:
    """This installation's concrete actions for Sesame5 state changes."""

    def __init__(
        self,
        cfg: AppConfig,
        *,
        sound_path: str,
        volume: float,
        repeat_gap: float,
    ) -> None:
        self.cfg = cfg
        self.sound = MacSoundLoop(
            sound_path,
            volume=volume,
            repeat_gap=repeat_gap,
        )
        if not self.sound.sound_path.is_file():
            raise FileNotFoundError(f"sound file not found: {self.sound.sound_path}")
        self.remo = NatureRemoClient(cfg.nature_token)
        self.nature_tasks: set[asyncio.Task[None]] = set()

    def log_event(self, event: str, **fields: object) -> None:
        print(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": event,
                    **fields,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    async def on_status(self, event: LockStateEvent) -> None:
        self.log_event("status", **event.status.to_json_dict())
        if event.is_initial or event.changed:
            self.log_event(
                "state_changed",
                from_state=(
                    None if event.previous_state is None else event.previous_state.value
                ),
                to_state=event.current_state.value,
            )
        if not event.changed:
            if event.status.is_unlocked:
                await self.sound.start()
            else:
                await self.sound.stop()

    async def on_unlocked(self, _event: LockStateEvent) -> None:
        self._schedule_nature_request(
            "light_button",
            self.cfg.nature_light_appliance_id,
            partial(
                self.remo.send_light_button,
                self.cfg.nature_light_appliance_id,
                self.cfg.nature_light_button,
            ),
            button=self.cfg.nature_light_button,
        )
        self._schedule_signal_sequence(self.cfg.nature_unlock_signal_ids)
        await self.sound.start()

    async def on_locked(self, _event: LockStateEvent) -> None:
        self._schedule_signal_sequence(self.cfg.nature_lock_signal_ids)
        await self.sound.stop()

    async def on_connection_lost(self) -> None:
        await self.sound.stop()

    async def handle_connection_event(self, event: str) -> None:
        self.log_event(event)

    async def handle_cycle_event(self, event: str, error: BaseException | None) -> None:
        if event == "cycle_timeout":
            self.log_event("monitor_timeout")
        elif event == "cycle_failed":
            assert error is not None
            self.log_event("monitor_error", error=str(error))
            print(f"sesame-remo error: {error}", file=sys.stderr, flush=True)

    async def close(self) -> None:
        await self.sound.stop()
        if self.nature_tasks:
            await asyncio.gather(*self.nature_tasks, return_exceptions=True)

    async def _send_nature_request(
        self,
        request_type: str,
        target_id: str,
        operation: Callable[[], None],
        *,
        button: str | None = None,
    ) -> None:
        try:
            await asyncio.to_thread(operation)
        except Exception as exc:
            self.log_event(
                "nature_request_completed",
                request_type=request_type,
                target_id=target_id,
                button=button,
                success=False,
                error=str(exc),
            )
        else:
            self.log_event(
                "nature_request_completed",
                request_type=request_type,
                target_id=target_id,
                button=button,
                success=True,
            )

    async def _send_signal_sequence(self, signal_ids: tuple[str, ...]) -> None:
        for signal_id in signal_ids:
            self.log_event(
                "nature_request_started",
                request_type="signal",
                target_id=signal_id,
                button=None,
            )
            await self._send_nature_request(
                "signal",
                signal_id,
                partial(self.remo.send_signal, signal_id),
            )

    def _track_nature_task(self, task: asyncio.Task[None]) -> None:
        self.nature_tasks.add(task)
        task.add_done_callback(self.nature_tasks.discard)

    def _schedule_signal_sequence(self, signal_ids: tuple[str, ...]) -> None:
        if signal_ids:
            self._track_nature_task(
                asyncio.create_task(self._send_signal_sequence(signal_ids))
            )

    def _schedule_nature_request(
        self,
        request_type: str,
        target_id: str,
        operation: Callable[[], None],
        *,
        button: str | None = None,
    ) -> None:
        self.log_event(
            "nature_request_started",
            request_type=request_type,
            target_id=target_id,
            button=button,
        )
        self._track_nature_task(
            asyncio.create_task(
                self._send_nature_request(
                    request_type,
                    target_id,
                    operation,
                    button=button,
                )
            )
        )
