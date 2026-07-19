from pathlib import Path

import pytest

from sesame_remo.automation.config import load_config


def test_load_config_requires_nature_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_id = "appliance"
nature_light_button = "on-100"
nature_unlock_signal_ids = ["on-signal", "blue-signal"]
nature_lock_signal_ids = ["on-signal", "green-signal"]
""".strip()
    )

    loaded = load_config(config)

    assert loaded.sesame.sesame_id == "10000000-0000-0000-0000-000000000000"
    assert loaded.sesame.sesame_secret_key == "00112233445566778899aabbccddeeff"
    assert loaded.nature_token == "token"
    assert loaded.nature_light_appliance_id == "appliance"
    assert loaded.nature_light_button == "on-100"
    assert loaded.nature_unlock_signal_ids == ("on-signal", "blue-signal")
    assert loaded.nature_lock_signal_ids == ("on-signal", "green-signal")


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


def test_load_config_defaults_signal_ids_to_empty(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_id = "appliance"
""".strip()
    )

    loaded = load_config(config)

    assert loaded.nature_unlock_signal_ids == ()
    assert loaded.nature_lock_signal_ids == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("nature_unlock_signal_ids", '[""]'),
        ("nature_lock_signal_ids", '["replace-me"]'),
        ("nature_unlock_signal_ids", '"not-an-array"'),
    ],
)
def test_load_config_rejects_invalid_signal_ids(
    tmp_path: Path, field: str, value: str
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_id = "appliance"
{field} = {value}
""".strip()
    )

    with pytest.raises(ValueError, match=field):
        load_config(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("nature_token", "   "),
        ("nature_light_appliance_id", "   "),
        ("nature_light_button", "   "),
    ],
)
def test_load_config_rejects_blank_nature_settings(
    tmp_path: Path, field: str, value: str
) -> None:
    values = {
        "nature_token": "token",
        "nature_light_appliance_id": "appliance",
        "nature_light_button": "on",
    }
    values[field] = value
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "{values["nature_token"]}"
nature_light_appliance_id = "{values["nature_light_appliance_id"]}"
nature_light_button = "{values["nature_light_button"]}"
""".strip()
    )

    with pytest.raises(ValueError):
        load_config(config)
