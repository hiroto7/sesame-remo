from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
import uuid


@dataclass(frozen=True)
class TouchProMatch:
    contains_hex: tuple[str, ...] = ()
    prefix_hex: str | None = None


@dataclass(frozen=True)
class Config:
    sesame_id: str
    sesame_secret_key: str
    nature_token: str = ""
    nature_light_appliance_id: str = ""
    nature_light_button: str = "on"
    cooldown_seconds: int = 30
    delete_history_after_read: bool = False
    touch_pro_match: TouchProMatch = field(default_factory=TouchProMatch)


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


def load_config(path: str | Path) -> Config:
    data = tomllib.loads(Path(path).read_text())
    matcher = data.get("touch_pro_match") or {}
    sesame_id = str(data["sesame_id"])
    try:
        parsed_sesame_id = uuid.UUID(sesame_id.replace("-", ""))
    except ValueError as exc:
        raise ValueError("sesame_id must be a UUID") from exc
    if parsed_sesame_id.int == 0:
        raise ValueError("sesame_id is still the placeholder; set your Sesame5 UUID")

    cooldown_seconds = int(data.get("cooldown_seconds", 30))
    if cooldown_seconds < 0:
        raise ValueError("cooldown_seconds must be zero or greater")

    secret_key = _validated_hex(
        str(data["sesame_secret_key"]), "sesame_secret_key", byte_length=16
    )
    if not any(bytes.fromhex(secret_key)):
        raise ValueError(
            "sesame_secret_key is still the placeholder; set your Sesame5 secret key"
        )

    return Config(
        sesame_id=sesame_id,
        sesame_secret_key=secret_key,
        nature_token=str(data.get("nature_token", "")),
        nature_light_appliance_id=str(data.get("nature_light_appliance_id", "")),
        nature_light_button=str(data.get("nature_light_button", "on")),
        cooldown_seconds=cooldown_seconds,
        delete_history_after_read=bool(data.get("delete_history_after_read", False)),
        touch_pro_match=TouchProMatch(
            contains_hex=tuple(
                _validated_hex(v, "touch_pro_match.contains_hex")
                for v in matcher.get("contains_hex", [])
            ),
            prefix_hex=(
                _validated_hex(matcher["prefix_hex"], "touch_pro_match.prefix_hex")
                if matcher.get("prefix_hex")
                else None
            ),
        ),
    )
