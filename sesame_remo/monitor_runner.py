from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .config import Config
from .sesame_client import SesameOS3Client, SesameScanTimeout
from .status import Sesame5MechanismStatus


StatusHandler = Callable[[Sesame5MechanismStatus], Awaitable[None]]
ConnectionEventHandler = Callable[[str], Awaitable[None]]
CycleEventHandler = Callable[[str, BaseException | None], Awaitable[None]]


async def run_monitor(
    cfg: Config,
    *,
    scan_timeout: float,
    poll_interval: float,
    status_handler: StatusHandler,
    connection_lost_handler: Callable[[], Awaitable[None]] | None = None,
    connection_event_handler: ConnectionEventHandler | None = None,
    cycle_event_handler: CycleEventHandler | None = None,
) -> None:
    if poll_interval < 0.0:
        raise ValueError("poll_interval must not be negative")

    while True:
        if cycle_event_handler is not None:
            await cycle_event_handler("cycle_started", None)
        try:
            client = SesameOS3Client(cfg.sesame_id, cfg.sesame_secret_key)
            await client.monitor_status(
                status_handler,
                scan_timeout=scan_timeout,
                connection_lost_handler=connection_lost_handler,
                connection_event_handler=connection_event_handler,
            )
        except SesameScanTimeout as exc:
            if connection_lost_handler is not None:
                await connection_lost_handler()
            if cycle_event_handler is not None:
                await cycle_event_handler("cycle_timeout", exc)
        except Exception as exc:
            if connection_lost_handler is not None:
                await connection_lost_handler()
            if cycle_event_handler is not None:
                await cycle_event_handler("cycle_failed", exc)
        finally:
            if cycle_event_handler is not None:
                await cycle_event_handler("cycle_finished", None)
        await asyncio.sleep(poll_interval)
