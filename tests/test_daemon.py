from sesame_remo.daemon import EventGate


def test_event_gate_blocks_duplicate_record_id() -> None:
    gate = EventGate(cooldown_seconds=30)
    assert gate.should_send("abc", now=100)
    assert not gate.should_send("abc", now=200)


def test_event_gate_blocks_cooldown() -> None:
    gate = EventGate(cooldown_seconds=30)
    assert gate.should_send("abc", now=100)
    assert not gate.should_send("def", now=120)
    assert gate.should_send("ghi", now=131)

