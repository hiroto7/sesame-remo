from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from ..core.config import SesameConfig


@dataclass(frozen=True)
class NatureSignalRef:
    appliance: str
    signal: str


@dataclass(frozen=True)
class AppConfig:
    sesame: SesameConfig
    nature_token: str
    nature_light_appliance_name: str
    nature_light_button: str = "on"
    nature_unlock_signals: tuple[NatureSignalRef, ...] = ()
    nature_lock_signals: tuple[NatureSignalRef, ...] = ()


def _required_string(
    data: dict[str, object],
    name: str,
    *,
    default: str | None = None,
    error_name: str | None = None,
) -> str:
    label = error_name or name
    value = data.get(name, default)
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned or cleaned == "replace-me":
        raise ValueError(f"{label} must be configured")
    return cleaned


def _validated_signals(
    data: dict[str, object], name: str
) -> tuple[NatureSignalRef, ...]:
    values = data.get(name, [])
    if not isinstance(values, list):
        raise ValueError(f"{name} must be an array of tables")

    signals: list[NatureSignalRef] = []
    for index, value in enumerate(values):
        item_name = f"{name}[{index}]"
        if not isinstance(value, dict):
            raise ValueError(f"{item_name} must be a table")
        if set(value) != {"appliance", "signal"}:
            raise ValueError(f"{item_name} must contain exactly appliance and signal")
        signals.append(
            NatureSignalRef(
                appliance=_required_string(
                    value, "appliance", error_name=f"{item_name}.appliance"
                ),
                signal=_required_string(
                    value, "signal", error_name=f"{item_name}.signal"
                ),
            )
        )
    return tuple(signals)


def load_config(path: str | Path) -> AppConfig:
    data = tomllib.loads(Path(path).read_text())
    sesame = SesameConfig.from_mapping(data)

    nature_token = _required_string(data, "nature_token")
    nature_light_appliance_name = _required_string(data, "nature_light_appliance_name")
    nature_light_button = _required_string(data, "nature_light_button", default="on")

    return AppConfig(
        sesame=sesame,
        nature_token=nature_token,
        nature_light_appliance_name=nature_light_appliance_name,
        nature_light_button=nature_light_button,
        nature_unlock_signals=_validated_signals(data, "nature_unlock_signals"),
        nature_lock_signals=_validated_signals(data, "nature_lock_signals"),
    )
