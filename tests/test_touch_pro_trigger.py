import pytest
from typing import cast

from sesame_remo.config import Config, TouchProMatch
from sesame_remo.history import HistoryRecord
from sesame_remo.nature import NatureRemoClient
from sesame_remo.touch_pro_trigger import EventGate, make_touch_pro_history_handler


def test_event_gate_blocks_duplicate_record_id() -> None:
    gate = EventGate(cooldown_seconds=30)
    assert gate.can_send("abc", now=100)
    gate.mark_sent("abc", now=100)
    assert not gate.can_send("abc", now=200)


def test_event_gate_blocks_cooldown() -> None:
    gate = EventGate(cooldown_seconds=30)
    assert gate.can_send("abc", now=100)
    gate.mark_sent("abc", now=100)
    assert not gate.can_send("def", now=120)
    assert gate.can_send("ghi", now=131)


def test_event_gate_does_not_consume_failed_attempt() -> None:
    gate = EventGate(cooldown_seconds=30)
    assert gate.can_send("abc", now=1)
    assert gate.can_send("abc", now=2)


@pytest.mark.asyncio
async def test_touch_pro_handler_continues_after_nature_failure() -> None:
    class FailingRemo:
        def send_light_on(self) -> None:
            raise OSError("temporary Nature API failure")

    events: list[tuple[str, dict[str, object] | None]] = []

    async def log_event(event: str, fields: dict[str, object] | None = None) -> None:
        events.append((event, fields))

    handler = make_touch_pro_history_handler(
        Config(
            sesame_id="10000000-0000-0000-0000-000000000000",
            sesame_secret_key="00112233445566778899aabbccddeeff",
            touch_pro_match=TouchProMatch(contains_hex=("aabb",)),
        ),
        cast(NatureRemoClient, FailingRemo()),
        EventGate(cooldown_seconds=0),
        log_event,
        lambda: None,
    )

    await handler(HistoryRecord(bytes.fromhex("1122334402aabb")))
    await handler(HistoryRecord(bytes.fromhex("5566778802aabb")))

    failures = [
        fields for event, fields in events if event == "nature_request_completed"
    ]
    assert len(failures) == 2
    assert all(fields is not None and fields["success"] is False for fields in failures)
