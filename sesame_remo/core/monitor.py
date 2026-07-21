from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from .config import SesameConfig
from .sesame_client import SesameOS3Client, SesameProtocolError, SesameScanTimeout
from .status import Sesame5MechanismStatus


class LockState(StrEnum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"


@dataclass(frozen=True)
class LockStateEvent:
    status: Sesame5MechanismStatus
    previous_status: Sesame5MechanismStatus | None

    @property
    def is_initial(self) -> bool:
        return self.previous_status is None

    @property
    def current_state(self) -> LockState:
        return LockState.LOCKED if self.status.is_locked else LockState.UNLOCKED

    @property
    def previous_state(self) -> LockState | None:
        if self.previous_status is None:
            return None
        return (
            LockState.LOCKED if self.previous_status.is_locked else LockState.UNLOCKED
        )

    @property
    def changed(self) -> bool:
        return (
            self.previous_state is not None
            and self.previous_state != self.current_state
        )


LockStateHandler = Callable[[LockStateEvent], Awaitable[None]]
ConnectionLostHandler = Callable[[], Awaitable[None]]
ConnectionEventHandler = Callable[[str], Awaitable[None]]
CycleEventHandler = Callable[[str, BaseException | None], Awaitable[None]]


async def run_lock_monitor(
    cfg: SesameConfig,
    *,
    scan_timeout: float,
    poll_interval: float,
    on_locked: LockStateHandler | None = None,
    on_unlocked: LockStateHandler | None = None,
    on_status: LockStateHandler | None = None,
    on_connection_lost: ConnectionLostHandler | None = None,
    connection_event_handler: ConnectionEventHandler | None = None,
    cycle_event_handler: CycleEventHandler | None = None,
) -> None:
    """Monitor Sesame5 and dispatch state transitions to caller-owned actions."""
    if poll_interval < 0.0:
        raise ValueError("poll_interval must not be negative")

    previous_status: Sesame5MechanismStatus | None = None
    protocol_retry_pending = False

    async def handle_status(status: Sesame5MechanismStatus) -> None:
        nonlocal previous_status, protocol_retry_pending
        protocol_retry_pending = False
        event = LockStateEvent(status=status, previous_status=previous_status)
        previous_status = status

        if on_status is not None:
            await on_status(event)
        if not event.changed:
            return
        if status.is_locked:
            if on_locked is not None:
                await on_locked(event)
        elif on_unlocked is not None:
            await on_unlocked(event)

    while True:
        suspend_monitor = False
        if cycle_event_handler is not None:
            await cycle_event_handler("cycle_started", None)
        try:
            client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)
            await client.monitor_status(
                handle_status,
                scan_timeout=scan_timeout,
                connection_lost_handler=on_connection_lost,
                connection_event_handler=connection_event_handler,
            )
        except SesameProtocolError as exc:
            if on_connection_lost is not None:
                await on_connection_lost()
            if cycle_event_handler is not None:
                await cycle_event_handler("cycle_protocol_error", exc)
            if protocol_retry_pending:
                suspend_monitor = True
                if cycle_event_handler is not None:
                    await cycle_event_handler("cycle_protocol_suspended", exc)
            else:
                protocol_retry_pending = True
        except SesameScanTimeout as exc:
            if on_connection_lost is not None:
                await on_connection_lost()
            if cycle_event_handler is not None:
                await cycle_event_handler("cycle_timeout", exc)
        except Exception as exc:
            if on_connection_lost is not None:
                await on_connection_lost()
            if cycle_event_handler is not None:
                await cycle_event_handler("cycle_failed", exc)
        finally:
            if cycle_event_handler is not None:
                await cycle_event_handler("cycle_finished", None)
        if suspend_monitor:
            await asyncio.Event().wait()
        await asyncio.sleep(poll_interval)
