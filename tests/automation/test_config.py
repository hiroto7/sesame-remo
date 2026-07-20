from pathlib import Path

import pytest

from sesame_remo.automation.config import NatureSignalRef, load_config


def test_load_config_requires_nature_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_name = "主照明"
nature_light_button = "on-100"
nature_unlock_signals = [
  { appliance = "間接照明", signal = "オン" },
  { appliance = "間接照明", signal = "B" },
]
nature_lock_signals = [
  { appliance = "間接照明", signal = "オン" },
  { appliance = "間接照明", signal = "G" },
]
""".strip()
    )

    loaded = load_config(config)

    assert loaded.sesame.sesame_id == "10000000-0000-0000-0000-000000000000"
    assert loaded.sesame.sesame_secret_key == "00112233445566778899aabbccddeeff"
    assert loaded.nature_token == "token"
    assert loaded.nature_light_appliance_name == "主照明"
    assert loaded.nature_light_button == "on-100"
    assert loaded.nature_unlock_signals == (
        NatureSignalRef("間接照明", "オン"),
        NatureSignalRef("間接照明", "B"),
    )
    assert loaded.nature_lock_signals == (
        NatureSignalRef("間接照明", "オン"),
        NatureSignalRef("間接照明", "G"),
    )


def test_load_config_rejects_missing_nature_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
""".strip()
    )

    with pytest.raises(ValueError, match="nature_token"):
        load_config(config)


def test_load_config_rejects_legacy_nature_id_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_id = "appliance-id"
nature_unlock_signal_ids = ["signal-id"]
nature_lock_signal_ids = ["signal-id"]
""".strip()
    )

    with pytest.raises(ValueError, match="nature_light_appliance_name"):
        load_config(config)


def test_load_config_defaults_button_and_signals(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_name = "主照明"
""".strip()
    )

    loaded = load_config(config)

    assert loaded.nature_light_button == "on"
    assert loaded.nature_unlock_signals == ()
    assert loaded.nature_lock_signals == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("nature_unlock_signals", '[{ appliance = "", signal = "オン" }]'),
        (
            "nature_lock_signals",
            '[{ appliance = "間接照明", signal = "replace-me" }]',
        ),
        ("nature_unlock_signals", '"not-an-array"'),
        ("nature_unlock_signals", '["not-a-table"]'),
        ("nature_unlock_signals", '[{ appliance = "間接照明" }]'),
        (
            "nature_unlock_signals",
            '[{ appliance = "間接照明", signal = "オン", id = "unused" }]',
        ),
    ],
)
def test_load_config_rejects_invalid_signals(
    tmp_path: Path, field: str, value: str
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_name = "主照明"
{field} = {value}
""".strip()
    )

    with pytest.raises(ValueError, match=field):
        load_config(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("nature_token", "   "),
        ("nature_light_appliance_name", "   "),
        ("nature_light_button", "   "),
    ],
)
def test_load_config_rejects_blank_nature_settings(
    tmp_path: Path, field: str, value: str
) -> None:
    values = {
        "nature_token": "token",
        "nature_light_appliance_name": "主照明",
        "nature_light_button": "on",
    }
    values[field] = value
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "{values["nature_token"]}"
nature_light_appliance_name = "{values["nature_light_appliance_name"]}"
nature_light_button = "{values["nature_light_button"]}"
""".strip()
    )

    with pytest.raises(ValueError):
        load_config(config)
