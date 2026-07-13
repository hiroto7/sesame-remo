from __future__ import annotations

from dataclasses import dataclass
from urllib import error, request


@dataclass(frozen=True)
class NatureRemoClient:
    token: str
    signal_id: str

    def send_light_on(self, timeout: float = 10.0) -> None:
        req = request.Request(
            f"https://api.nature.global/1/signals/{self.signal_id}/send",
            method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            data=b"",
        )
        try:
            with request.urlopen(req, timeout=timeout) as res:
                if res.status < 200 or res.status >= 300:
                    raise RuntimeError(f"Nature Remo API returned HTTP {res.status}")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Nature Remo API returned HTTP {exc.code}: {body}"
            ) from exc
