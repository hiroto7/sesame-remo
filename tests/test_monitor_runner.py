import pytest

from sesame_remo.config import Config
from sesame_remo.monitor_runner import run_monitor
from sesame_remo.status import Sesame5MechanismStatus


@pytest.mark.asyncio
async def test_run_monitor_reuses_common_cycle_and_handler_wiring(monkeypatch) -> None:
    status = Sesame5MechanismStatus(bytes.fromhex("00000000341200"))
    events: list[str] = []
    received_status: list[Sesame5MechanismStatus] = []

    class StopMonitor(Exception):
        pass

    class FakeClient:
        def __init__(self, _sesame_id: str, _secret_key: str) -> None:
            pass

        async def monitor_status(self, status_handler, **kwargs) -> None:
            assert kwargs["history_handler"] is not None
            assert kwargs["history_event_handler"] is not None
            await status_handler(status)
            raise StopMonitor

    async def handle_status(value: Sesame5MechanismStatus) -> None:
        received_status.append(value)

    async def handle_cycle(event: str, _error: BaseException | None) -> None:
        events.append(event)
        if event == "cycle_finished":
            raise StopMonitor

    monkeypatch.setattr("sesame_remo.monitor_runner.SesameOS3Client", FakeClient)

    async def handle_history(_record) -> None:
        return None

    async def handle_history_event(_event: str, _fields) -> None:
        return None

    with pytest.raises(StopMonitor):
        await run_monitor(
            Config(
                sesame_id="10000000-0000-0000-0000-000000000000",
                sesame_secret_key="00112233445566778899aabbccddeeff",
            ),
            scan_timeout=1,
            poll_interval=0,
            status_handler=handle_status,
            history_handler=handle_history,
            history_event_handler=handle_history_event,
            cycle_event_handler=handle_cycle,
        )

    assert events == ["cycle_started", "cycle_failed", "cycle_finished"]
    assert received_status == [status]
