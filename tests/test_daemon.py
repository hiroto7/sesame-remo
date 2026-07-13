from sesame_remo.daemon import EventGate


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
