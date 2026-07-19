from pathlib import Path

import pytest

from sesame_remo.core.config import load_sesame_config


def test_load_sesame_config_accepts_config_without_automation_settings(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
""".strip()
    )

    loaded = load_sesame_config(config)

    assert loaded.sesame_id == "10000000-0000-0000-0000-000000000000"
    assert loaded.sesame_secret_key == "00112233445566778899aabbccddeeff"


def test_load_sesame_config_rejects_placeholder_sesame_id(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "00000000-0000-0000-0000-000000000000"
sesame_secret_key = "00112233445566778899aabbccddeeff"
""".strip()
    )

    with pytest.raises(ValueError, match="placeholder"):
        load_sesame_config(config)
