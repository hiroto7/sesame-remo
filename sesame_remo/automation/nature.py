from __future__ import annotations

from dataclasses import dataclass
from urllib import error, parse, request


@dataclass(frozen=True)
class NatureRemoClient:
    token: str

    def send_light_button(
        self,
        appliance_id: str,
        button: str,
        timeout: float = 10.0,
    ) -> None:
        self._post(
            f"/1/appliances/{appliance_id}/light",
            data=parse.urlencode({"button": button}).encode(),
            timeout=timeout,
        )

    def send_signal(self, signal_id: str, timeout: float = 10.0) -> None:
        self._post(f"/1/signals/{signal_id}/send", timeout=timeout)

    def _post(
        self,
        path: str,
        *,
        data: bytes | None = None,
        timeout: float,
    ) -> None:
        headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = request.Request(
            f"https://api.nature.global{path}",
            method="POST",
            headers=headers,
            data=data,
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
