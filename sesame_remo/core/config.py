from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import tomllib
import uuid


@dataclass(frozen=True)
class SesameConfig:
    sesame_id: str
    sesame_secret_key: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> SesameConfig:
        sesame_id = str(data["sesame_id"])
        try:
            parsed_sesame_id = uuid.UUID(sesame_id.replace("-", ""))
        except ValueError as exc:
            raise ValueError("sesame_id must be a UUID") from exc
        if parsed_sesame_id.int == 0:
            raise ValueError(
                "sesame_id is still the placeholder; set your Sesame5 UUID"
            )

        secret_key = _validated_hex(
            str(data["sesame_secret_key"]),
            "sesame_secret_key",
            byte_length=16,
        )
        if not any(bytes.fromhex(secret_key)):
            raise ValueError(
                "sesame_secret_key is still the placeholder; "
                "set your Sesame5 secret key"
            )
        return cls(sesame_id=sesame_id, sesame_secret_key=secret_key)


def load_sesame_config(path: str | Path) -> SesameConfig:
    return SesameConfig.from_mapping(tomllib.loads(Path(path).read_text()))


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
