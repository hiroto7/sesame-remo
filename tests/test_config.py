from pathlib import Path

import pytest

from sesame_remo.config import load_config


def test_load_config_requires_nature_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_id = "appliance"
nature_light_button = "on-100"
""".strip()
    )

    loaded = load_config(config)

    assert loaded.nature_token == "token"
    assert loaded.nature_light_appliance_id == "appliance"
    assert loaded.nature_light_button == "on-100"


def test_load_config_rejects_missing_nature_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
""".strip()
    )

    with pytest.raises(KeyError, match="nature_token"):
        load_config(config)


def test_load_config_rejects_placeholder_sesame_id(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "00000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
nature_token = "token"
nature_light_appliance_id = "appliance"
""".strip()
    )

    with pytest.raises(ValueError, match="placeholder"):
        load_config(config)
