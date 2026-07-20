from __future__ import annotations

from dataclasses import dataclass
import json
from urllib import error, parse, request

from .config import AppConfig, NatureSignalRef


@dataclass(frozen=True)
class NatureSignal:
    id: str
    name: str


@dataclass(frozen=True)
class NatureAppliance:
    id: str
    nickname: str
    type: str
    signals: tuple[NatureSignal, ...]


@dataclass(frozen=True)
class ResolvedNatureTargets:
    light_appliance_id: str
    unlock_signal_ids: tuple[str, ...]
    lock_signal_ids: tuple[str, ...]


def _json_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Nature Remo API returned an invalid {field}")
    return value


def _parse_appliances(payload: object) -> tuple[NatureAppliance, ...]:
    if not isinstance(payload, list):
        raise RuntimeError("Nature Remo API returned an invalid appliance list")

    appliances: list[NatureAppliance] = []
    for appliance_index, value in enumerate(payload):
        if not isinstance(value, dict):
            raise RuntimeError(
                f"Nature Remo API returned an invalid appliance at index {appliance_index}"
            )
        raw_signals = value.get("signals")
        if raw_signals is None:
            raw_signals = []
        if not isinstance(raw_signals, list):
            raise RuntimeError(
                "Nature Remo API returned invalid signals for "
                f"appliance at index {appliance_index}"
            )
        signals: list[NatureSignal] = []
        for signal_index, raw_signal in enumerate(raw_signals):
            if not isinstance(raw_signal, dict):
                raise RuntimeError(
                    "Nature Remo API returned an invalid signal at "
                    f"appliance index {appliance_index}, signal index {signal_index}"
                )
            signals.append(
                NatureSignal(
                    id=_json_string(raw_signal.get("id"), "signal id"),
                    name=_json_string(raw_signal.get("name"), "signal name"),
                )
            )
        appliances.append(
            NatureAppliance(
                id=_json_string(value.get("id"), "appliance id"),
                nickname=_json_string(value.get("nickname"), "appliance nickname"),
                type=_json_string(value.get("type"), "appliance type"),
                signals=tuple(signals),
            )
        )
    return tuple(appliances)


def _resolve_signal(
    appliances: tuple[NatureAppliance, ...], ref: NatureSignalRef
) -> str:
    matches = [
        signal.id
        for appliance in appliances
        if appliance.nickname == ref.appliance
        for signal in appliance.signals
        if signal.name == ref.signal
    ]
    target = f"{ref.appliance} / {ref.signal}"
    if not matches:
        raise RuntimeError(f'Nature Remo signal not found: "{target}"')
    if len(matches) > 1:
        raise RuntimeError(f'Nature Remo signal name is ambiguous: "{target}"')
    return matches[0]


def resolve_nature_targets(
    config: AppConfig, appliances: tuple[NatureAppliance, ...]
) -> ResolvedNatureTargets:
    same_name = [
        appliance
        for appliance in appliances
        if appliance.nickname == config.nature_light_appliance_name
    ]
    light_matches = [appliance for appliance in same_name if appliance.type == "LIGHT"]
    if not light_matches:
        if same_name:
            raise RuntimeError(
                "Nature Remo appliance is not a LIGHT appliance: "
                f'"{config.nature_light_appliance_name}"'
            )
        raise RuntimeError(
            "Nature Remo LIGHT appliance not found: "
            f'"{config.nature_light_appliance_name}"'
        )
    if len(light_matches) > 1:
        raise RuntimeError(
            "Nature Remo LIGHT appliance name is ambiguous: "
            f'"{config.nature_light_appliance_name}"'
        )

    return ResolvedNatureTargets(
        light_appliance_id=light_matches[0].id,
        unlock_signal_ids=tuple(
            _resolve_signal(appliances, ref) for ref in config.nature_unlock_signals
        ),
        lock_signal_ids=tuple(
            _resolve_signal(appliances, ref) for ref in config.nature_lock_signals
        ),
    )


@dataclass(frozen=True)
class NatureRemoClient:
    token: str

    def get_appliances(self, timeout: float = 10.0) -> tuple[NatureAppliance, ...]:
        req = request.Request(
            "https://api.nature.global/1/appliances",
            method="GET",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with request.urlopen(req, timeout=timeout) as res:
                if res.status < 200 or res.status >= 300:
                    raise RuntimeError(f"Nature Remo API returned HTTP {res.status}")
                payload = json.loads(res.read())
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Nature Remo API returned HTTP {exc.code}: {body}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Nature Remo API request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("Nature Remo API request timed out") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Nature Remo API returned invalid JSON") from exc
        return _parse_appliances(payload)

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
