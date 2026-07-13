from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class TouchProMatch:
    contains_hex: tuple[str, ...] = ()
    prefix_hex: str | None = None


@dataclass(frozen=True)
class Config:
    sesame_id: str
    sesame_secret_key: str
    nature_token: str
    nature_light_on_signal_id: str
    cooldown_seconds: int = 30
    delete_history_after_read: bool = False
    touch_pro_match: TouchProMatch = field(default_factory=TouchProMatch)


def _clean_hex(value: str) -> str:
    return value.replace(" ", "").replace(":", "").replace("-", "").lower()


def load_config(path: str | Path) -> Config:
    data = tomllib.loads(Path(path).read_text())
    matcher = data.get("touch_pro_match") or {}
    return Config(
        sesame_id=str(data["sesame_id"]),
        sesame_secret_key=_clean_hex(str(data["sesame_secret_key"])),
        nature_token=str(data["nature_token"]),
        nature_light_on_signal_id=str(data["nature_light_on_signal_id"]),
        cooldown_seconds=int(data.get("cooldown_seconds", 30)),
        delete_history_after_read=bool(data.get("delete_history_after_read", False)),
        touch_pro_match=TouchProMatch(
            contains_hex=tuple(_clean_hex(v) for v in matcher.get("contains_hex", [])),
            prefix_hex=_clean_hex(matcher["prefix_hex"]) if matcher.get("prefix_hex") else None,
        ),
    )
