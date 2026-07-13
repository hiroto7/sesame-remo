from sesame_remo.config import TouchProMatch
from sesame_remo.history import HistoryRecord, is_touch_pro_history


TOUCH_PRO_SOURCE_TAG = "00112233445566778899aabbccddeeff"
TOUCH_PRO_UNLOCK_1 = bytes.fromhex(
    "01000000020102030405060708090a0b0c0d00" + TOUCH_PRO_SOURCE_TAG
)
TOUCH_PRO_UNLOCK_2 = bytes.fromhex(
    "02000000021112131405060708090e0b0c0d00" + TOUCH_PRO_SOURCE_TAG
)
APP_UNLOCK = bytes.fromhex(
    "03000000022122232405060708090f0b0c0d00ffeeddccbbaa99887766554433221100"
)
MANUAL_UNLOCK = bytes.fromhex("0400000008313233340506000708090a0b")


def test_history_record_uses_first_four_bytes_as_record_id() -> None:
    record = HistoryRecord(bytes.fromhex("0102030402bbcc"))
    assert record.record_id == "01020304"
    assert record.payload_hex == "0102030402bbcc"
    assert record.event_type == 2
    assert record.is_unlock


def test_history_record_recognizes_lock_event() -> None:
    record = HistoryRecord(bytes.fromhex("0102030401bbcc"))
    assert not record.is_unlock


def test_history_record_recognizes_manual_unlock_event() -> None:
    record = HistoryRecord(MANUAL_UNLOCK)
    assert record.event_type == 8
    assert record.is_unlock


def test_touch_pro_match_requires_configured_pattern() -> None:
    assert not is_touch_pro_history(bytes.fromhex("01020304"), TouchProMatch())


def test_touch_pro_match_contains_all_patterns() -> None:
    matcher = TouchProMatch(contains_hex=("aabb", "eeff"))
    assert is_touch_pro_history(bytes.fromhex("010203040011aabb22eeff"), matcher)
    assert not is_touch_pro_history(bytes.fromhex("010203040011aabb22"), matcher)


def test_touch_pro_match_prefix_and_contains() -> None:
    matcher = TouchProMatch(prefix_hex="0102", contains_hex=("aabb",))
    assert is_touch_pro_history(bytes.fromhex("a1a2a3a4010233aabb"), matcher)
    assert not is_touch_pro_history(bytes.fromhex("a1a2a3a499010233aabb"), matcher)


def test_touch_pro_match_accepts_prefix_only() -> None:
    matcher = TouchProMatch(prefix_hex="02aabb")
    assert is_touch_pro_history(bytes.fromhex("a1a2a3a402aabbcc"), matcher)
    assert not is_touch_pro_history(bytes.fromhex("a1a2a3a401aabbcc"), matcher)


def test_touch_pro_match_ignores_record_id() -> None:
    matcher = TouchProMatch(contains_hex=("aabb",))
    assert not is_touch_pro_history(bytes.fromhex("aabb000100112233"), matcher)


def test_real_shape_fixtures_distinguish_touch_pro_from_app_and_manual() -> None:
    matcher = TouchProMatch(contains_hex=(TOUCH_PRO_SOURCE_TAG,))

    assert is_touch_pro_history(TOUCH_PRO_UNLOCK_1, matcher)
    assert is_touch_pro_history(TOUCH_PRO_UNLOCK_2, matcher)
    assert not is_touch_pro_history(APP_UNLOCK, matcher)
    assert not is_touch_pro_history(MANUAL_UNLOCK, matcher)
