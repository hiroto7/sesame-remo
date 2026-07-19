from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from ..core.config import SesameConfig


@dataclass(frozen=True)
class AppConfig:
    sesame: SesameConfig
    nature_token: str
    nature_light_appliance_id: str
    nature_light_button: str = "on"
    nature_unlock_signal_ids: tuple[str, ...] = ()
    nature_lock_signal_ids: tuple[str, ...] = ()


def _validated_signal_ids(data: dict[str, object], name: str) -> tuple[str, ...]:
    values = data.get(name, [])
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise ValueError(f"{name} must be an array of strings")
    cleaned = tuple(value.strip() for value in values)
    if any(not value or value == "replace-me" for value in cleaned):
        raise ValueError(f"{name} must not contain empty or placeholder values")
    return cleaned


def load_config(path: str | Path) -> AppConfig:
    data = tomllib.loads(Path(path).read_text())
    sesame = SesameConfig.from_mapping(data)

    nature_token = str(data.get("nature_token", "")).strip()
    if not nature_token or nature_token == "replace-me":
        raise ValueError("nature_token must be configured")
    nature_light_appliance_id = str(data.get("nature_light_appliance_id", "")).strip()
    if not nature_light_appliance_id or nature_light_appliance_id == "replace-me":
        raise ValueError("nature_light_appliance_id must be configured")
    nature_light_button = str(data.get("nature_light_button", "on")).strip()
    if not nature_light_button:
        raise ValueError("nature_light_button must not be empty")

    return AppConfig(
        sesame=sesame,
        nature_token=nature_token,
        nature_light_appliance_id=nature_light_appliance_id,
        nature_light_button=nature_light_button,
        nature_unlock_signal_ids=_validated_signal_ids(
            data, "nature_unlock_signal_ids"
        ),
        nature_lock_signal_ids=_validated_signal_ids(data, "nature_lock_signal_ids"),
    )
