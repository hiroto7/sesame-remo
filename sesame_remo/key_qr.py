from base64 import b64decode
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse
import uuid


SESAME5_PRODUCT_TYPES = {5, 7, 16}


@dataclass(frozen=True)
class SesameKey:
    device_id: uuid.UUID
    secret_key: bytes


def decode_sesame5_share_url(url: str) -> SesameKey:
    query = parse_qs(urlparse(url.strip()).query)
    if query.get("t") != ["sk"] or "sk" not in query:
        raise ValueError("input is not a Sesame key share URL")
    try:
        payload = b64decode(query["sk"][0], validate=True)
    except ValueError as exc:
        raise ValueError("Sesame share key is not valid Base64") from exc
    if len(payload) != 39:
        raise ValueError(f"unexpected Sesame5 share key length: {len(payload)} bytes")
    if payload[0] not in SESAME5_PRODUCT_TYPES:
        raise ValueError(f"share key is not for Sesame5: product_type={payload[0]}")

    secret_key = payload[1:17]
    # This is the same guest-key test used by the official Android SDK.
    if "000000" in secret_key.hex():
        raise ValueError(
            "guest keys require Candy House server authentication; use an owner or manager share key"
        )
    return SesameKey(device_id=uuid.UUID(bytes=payload[23:39]), secret_key=secret_key)
