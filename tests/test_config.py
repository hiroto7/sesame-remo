from pathlib import Path

from sesame_remo.config import load_config


def test_load_config_with_touch_pro_match(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
sesame_id = "10000000-0000-0000-0000-000000000000"
sesame_secret_key = "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff"
nature_token = "token"
nature_light_appliance_id = "appliance"
nature_light_button = "on-100"
cooldown_seconds = 12
delete_history_after_read = true

[touch_pro_match]
contains_hex = ["aa:bb", "cc-dd"]
prefix_hex = "00 01"
""".strip()
    )

    loaded = load_config(config)

    assert loaded.sesame_secret_key == "00112233445566778899aabbccddeeff"
    assert loaded.cooldown_seconds == 12
    assert loaded.delete_history_after_read is True
    assert loaded.nature_light_appliance_id == "appliance"
    assert loaded.nature_light_button == "on-100"
    assert loaded.touch_pro_match.contains_hex == ("aabb", "ccdd")
    assert loaded.touch_pro_match.prefix_hex == "0001"


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

    try:
        load_config(config)
    except ValueError as exc:
        assert "placeholder" in str(exc)
    else:
        raise AssertionError("placeholder Sesame ID was accepted")
