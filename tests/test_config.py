from pathlib import Path

from sesame_remo.config import load_config


def test_load_config_with_touch_pro_match(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "00000000-0000-0000-0000-000000000000"
sesame_secret_key = "00:11-22 33"
nature_token = "token"
nature_light_on_signal_id = "signal"
cooldown_seconds = 12
delete_history_after_read = true

[touch_pro_match]
contains_hex = ["aa:bb", "cc-dd"]
prefix_hex = "00 01"
""".strip()
    )

    loaded = load_config(config)

    assert loaded.sesame_secret_key == "00112233"
    assert loaded.cooldown_seconds == 12
    assert loaded.delete_history_after_read is True
    assert loaded.touch_pro_match.contains_hex == ("aabb", "ccdd")
    assert loaded.touch_pro_match.prefix_hex == "0001"

