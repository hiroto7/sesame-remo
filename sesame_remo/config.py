from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
import uuid


@dataclass(frozen=True)
class Config:
    sesame_id: str
    sesame_secret_key: str
    nature_token: str = ""
    nature_light_appliance_id: str = ""
    nature_light_button: str = "on"
    nature_unlock_signal_ids: tuple[str, ...] = ()
    nature_lock_signal_ids: tuple[str, ...] = ()


def _clean_hex(value: str) -> str:
    return value.replace(" ", "").replace(":", "").replace("-", "").lower()


def _validated_hex(value: str, name: str, *, byte_length: int | None = None) -> str:
    cleaned = _clean_hex(value)
    if not cleaned:
        raise ValueError(f"{name} must not be empty")
    try:
        decoded = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(f"{name} must be hexadecimal") from exc
    if byte_length is not None and len(decoded) != byte_length:
        raise ValueError(f"{name} must be exactly {byte_length} bytes")
    return cleaned


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


def load_config(path: str | Path, *, require_nature: bool = True) -> Config:
    data = tomllib.loads(Path(path).read_text())
    sesame_id = str(data["sesame_id"])
    try:
        parsed_sesame_id = uuid.UUID(sesame_id.replace("-", ""))
    except ValueError as exc:
        raise ValueError("sesame_id must be a UUID") from exc
    if parsed_sesame_id.int == 0:
        raise ValueError("sesame_id is still the placeholder; set your Sesame5 UUID")

    secret_key = _validated_hex(
        str(data["sesame_secret_key"]), "sesame_secret_key", byte_length=16
    )
    if not any(bytes.fromhex(secret_key)):
        raise ValueError(
            "sesame_secret_key is still the placeholder; set your Sesame5 secret key"
        )

    nature_token = str(data.get("nature_token", "")).strip()
    if require_nature and (not nature_token or nature_token == "replace-me"):
        raise ValueError("nature_token must be configured")
    nature_light_appliance_id = str(data.get("nature_light_appliance_id", "")).strip()
    if require_nature and (
        not nature_light_appliance_id or nature_light_appliance_id == "replace-me"
    ):
        raise ValueError("nature_light_appliance_id must be configured")
    nature_light_button = str(data.get("nature_light_button", "on")).strip()
    if require_nature and not nature_light_button:
        raise ValueError("nature_light_button must not be empty")
    nature_unlock_signal_ids = (
        _validated_signal_ids(data, "nature_unlock_signal_ids")
        if require_nature
        else ()
    )
    nature_lock_signal_ids = (
        _validated_signal_ids(data, "nature_lock_signal_ids") if require_nature else ()
    )

    return Config(
        sesame_id=sesame_id,
        sesame_secret_key=secret_key,
        nature_token=nature_token,
        nature_light_appliance_id=nature_light_appliance_id,
        nature_light_button=nature_light_button,
        nature_unlock_signal_ids=nature_unlock_signal_ids,
        nature_lock_signal_ids=nature_lock_signal_ids,
    )
