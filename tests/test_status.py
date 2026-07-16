import pytest

from sesame_remo.status import Sesame5MechanismStatus, is_mech_status_publish


def test_mechanism_status_reads_lock_flag_and_position() -> None:
    status = Sesame5MechanismStatus(bytes.fromhex("00000000341202"))

    assert status.is_locked
    assert not status.is_unlocked
    assert status.position == 0x1234


def test_mechanism_status_without_lock_flag_is_unlocked() -> None:
    status = Sesame5MechanismStatus(bytes.fromhex("00000000341200"))

    assert not status.is_locked
    assert status.is_unlocked


def test_mechanism_status_rejects_short_payload() -> None:
    with pytest.raises(ValueError, match="at least 7 bytes"):
        Sesame5MechanismStatus(b"123456")


def test_mech_status_item_code() -> None:
    assert is_mech_status_publish(81)
    assert not is_mech_status_publish(4)


def test_mechanism_status_serializes_as_json_line() -> None:
    status = Sesame5MechanismStatus(bytes.fromhex("00000000341202"))

    assert '"is_locked": true' in status.to_json_line()
