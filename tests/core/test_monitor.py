import pytest

from sesame_remo.core.config import SesameConfig
from sesame_remo.core.monitor import LockState, LockStateEvent, run_lock_monitor
from sesame_remo.core.sesame_client import SesameProtocolError, SesameScanTimeout
from sesame_remo.core.status import Sesame5MechanismStatus


@pytest.mark.asyncio
async def test_run_lock_monitor_dispatches_only_real_transitions(monkeypatch) -> None:
    statuses = [
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341200")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341200")),
        Sesame5MechanismStatus(bytes.fromhex("00000000341202")),
    ]
    observed: list[LockStateEvent] = []
    locked: list[LockStateEvent] = []
    unlocked: list[LockStateEvent] = []

    class StopMonitor(Exception):
        pass

    class FakeClient:
        def __init__(self, _sesame_id: str, _secret_key: str) -> None:
            pass

        async def monitor_status(self, status_handler, **kwargs) -> None:
            assert "history_handler" not in kwargs
            assert "history_event_handler" not in kwargs
            for status in statuses:
                await status_handler(status)
            raise StopMonitor

    monkeypatch.setattr("sesame_remo.core.monitor.SesameOS3Client", FakeClient)

    async def handle_cycle(event: str, _error: BaseException | None) -> None:
        if event == "cycle_failed":
            raise StopMonitor

    async def handle_status(event: LockStateEvent) -> None:
        observed.append(event)

    async def handle_locked(event: LockStateEvent) -> None:
        locked.append(event)

    async def handle_unlocked(event: LockStateEvent) -> None:
        unlocked.append(event)

    with pytest.raises(StopMonitor):
        await run_lock_monitor(
            SesameConfig(
                sesame_id="10000000-0000-0000-0000-000000000000",
                sesame_secret_key="00112233445566778899aabbccddeeff",
            ),
            scan_timeout=1,
            poll_interval=0,
            on_locked=handle_locked,
            on_unlocked=handle_unlocked,
            on_status=handle_status,
            cycle_event_handler=handle_cycle,
        )

    assert len(observed) == 5
    assert observed[0].is_initial
    assert observed[0].current_state is LockState.LOCKED
    assert observed[0].previous_state is None
    assert not observed[1].changed
    assert len(unlocked) == 1
    assert unlocked[0].current_state is LockState.UNLOCKED
    assert unlocked[0].previous_state is LockState.LOCKED
    assert unlocked[0].previous_status is statuses[1]
    assert len(locked) == 1
    assert locked[0].previous_status is statuses[3]


def test_core_config_has_no_automation_settings() -> None:
    config = SesameConfig(
        sesame_id="10000000-0000-0000-0000-000000000000",
        sesame_secret_key="00112233445566778899aabbccddeeff",
    )

    assert not hasattr(config, "nature_token")


@pytest.mark.asyncio
async def test_session_replaced_stops_without_retry(monkeypatch) -> None:
    client_count = 0
    cycle_events: list[str] = []

    class FakeClient:
        def __init__(self, _sesame_id: str, _secret_key: str) -> None:
            nonlocal client_count
            client_count += 1

        async def monitor_status(self, _status_handler, **_kwargs) -> None:
            raise SesameProtocolError("session_replaced")

    async def handle_cycle(event: str, _error: BaseException | None) -> None:
        cycle_events.append(event)

    monkeypatch.setattr("sesame_remo.core.monitor.SesameOS3Client", FakeClient)
    await run_lock_monitor(
        SesameConfig(
            sesame_id="10000000-0000-0000-0000-000000000000",
            sesame_secret_key="00112233445566778899aabbccddeeff",
        ),
        scan_timeout=1,
        poll_interval=0,
        cycle_event_handler=handle_cycle,
    )

    assert client_count == 1
    assert cycle_events.count("cycle_protocol_error") == 1
    assert cycle_events.count("cycle_protocol_stopped") == 1


@pytest.mark.asyncio
async def test_notification_processing_failure_retries_once_then_stops(
    monkeypatch,
) -> None:
    client_count = 0
    cycle_events: list[str] = []

    class FakeClient:
        def __init__(self, _sesame_id: str, _secret_key: str) -> None:
            nonlocal client_count
            client_count += 1

        async def monitor_status(self, _status_handler, **_kwargs) -> None:
            raise SesameProtocolError("notification_processing_failed")

    async def handle_cycle(event: str, _error: BaseException | None) -> None:
        cycle_events.append(event)

    monkeypatch.setattr("sesame_remo.core.monitor.SesameOS3Client", FakeClient)

    await run_lock_monitor(
        SesameConfig(
            sesame_id="10000000-0000-0000-0000-000000000000",
            sesame_secret_key="00112233445566778899aabbccddeeff",
        ),
        scan_timeout=1,
        poll_interval=0,
        cycle_event_handler=handle_cycle,
    )

    assert client_count == 2
    assert cycle_events.count("cycle_protocol_error") == 2
    assert cycle_events.count("cycle_protocol_stopped") == 1


@pytest.mark.asyncio
async def test_status_after_protocol_retry_reenables_one_retry(monkeypatch) -> None:
    status = Sesame5MechanismStatus(bytes.fromhex("00000000341202"))
    client_count = 0

    class StopMonitor(Exception):
        pass

    class FakeClient:
        def __init__(self, _sesame_id: str, _secret_key: str) -> None:
            nonlocal client_count
            client_count += 1
            self.number = client_count

        async def monitor_status(self, status_handler, **_kwargs) -> None:
            if self.number == 1:
                raise SesameProtocolError("notification_processing_failed")
            if self.number == 2:
                await status_handler(status)
                raise SesameProtocolError("notification_processing_failed")
            raise StopMonitor

    async def handle_cycle(event: str, _error: BaseException | None) -> None:
        if event == "cycle_failed":
            raise StopMonitor

    monkeypatch.setattr("sesame_remo.core.monitor.SesameOS3Client", FakeClient)

    with pytest.raises(StopMonitor):
        await run_lock_monitor(
            SesameConfig(
                sesame_id="10000000-0000-0000-0000-000000000000",
                sesame_secret_key="00112233445566778899aabbccddeeff",
            ),
            scan_timeout=1,
            poll_interval=0,
            cycle_event_handler=handle_cycle,
        )

    assert client_count == 3


@pytest.mark.asyncio
async def test_run_lock_monitor_preserves_state_across_reconnects(monkeypatch) -> None:
    locked_status = Sesame5MechanismStatus(bytes.fromhex("00000000341202"))
    unlocked_status = Sesame5MechanismStatus(bytes.fromhex("00000000341200"))
    client_count = 0
    unlocked: list[LockStateEvent] = []

    class StopMonitor(Exception):
        pass

    class FakeClient:
        def __init__(self, _sesame_id: str, _secret_key: str) -> None:
            nonlocal client_count
            client_count += 1
            self.number = client_count

        async def monitor_status(self, status_handler, **_kwargs) -> None:
            if self.number == 1:
                await status_handler(locked_status)
                raise SesameScanTimeout("reconnect")
            await status_handler(unlocked_status)
            raise StopMonitor

    monkeypatch.setattr("sesame_remo.core.monitor.SesameOS3Client", FakeClient)

    async def handle_unlocked(event: LockStateEvent) -> None:
        unlocked.append(event)

    async def handle_cycle(event: str, _error: BaseException | None) -> None:
        if event == "cycle_failed":
            raise StopMonitor

    with pytest.raises(StopMonitor):
        await run_lock_monitor(
            SesameConfig(
                sesame_id="10000000-0000-0000-0000-000000000000",
                sesame_secret_key="00112233445566778899aabbccddeeff",
            ),
            scan_timeout=1,
            poll_interval=0,
            on_unlocked=handle_unlocked,
            cycle_event_handler=handle_cycle,
        )

    assert client_count == 2
    assert len(unlocked) == 1
    assert unlocked[0].previous_status is locked_status
