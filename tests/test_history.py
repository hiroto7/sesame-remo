from sesame_remo.config import TouchProMatch
from sesame_remo.history import HistoryRecord, is_touch_pro_history


def test_history_record_uses_first_four_bytes_as_record_id() -> None:
    record = HistoryRecord(bytes.fromhex("01020304aabbcc"))
    assert record.record_id == "01020304"
    assert record.payload_hex == "01020304aabbcc"


def test_touch_pro_match_requires_configured_pattern() -> None:
    assert not is_touch_pro_history(bytes.fromhex("01020304"), TouchProMatch())


def test_touch_pro_match_contains_all_patterns() -> None:
    matcher = TouchProMatch(contains_hex=("aabb", "eeff"))
    assert is_touch_pro_history(bytes.fromhex("0011aabb22eeff"), matcher)
    assert not is_touch_pro_history(bytes.fromhex("0011aabb22"), matcher)


def test_touch_pro_match_prefix_and_contains() -> None:
    matcher = TouchProMatch(prefix_hex="0102", contains_hex=("aabb",))
    assert is_touch_pro_history(bytes.fromhex("010233aabb"), matcher)
    assert not is_touch_pro_history(bytes.fromhex("99010233aabb"), matcher)

