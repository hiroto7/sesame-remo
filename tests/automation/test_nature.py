import json
from urllib import parse

import pytest

from sesame_remo.automation import nature
from sesame_remo.automation.config import AppConfig, NatureSignalRef
from sesame_remo.automation.nature import (
    NatureAppliance,
    NatureRemoClient,
    NatureSignal,
    resolve_nature_targets,
)
from sesame_remo.core.config import SesameConfig


class FakeResponse:
    status = 200

    def __init__(self, body: bytes = b"") -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _config(
    *,
    light_name: str = "主照明",
    unlock_signals: tuple[NatureSignalRef, ...] = (
        NatureSignalRef("間接照明", "オン"),
        NatureSignalRef("間接照明", "B"),
    ),
    lock_signals: tuple[NatureSignalRef, ...] = (
        NatureSignalRef("間接照明", "オン"),
        NatureSignalRef("間接照明", "G"),
    ),
) -> AppConfig:
    return AppConfig(
        sesame=SesameConfig(
            sesame_id="10000000-0000-0000-0000-000000000000",
            sesame_secret_key="00112233445566778899aabbccddeeff",
        ),
        nature_token="token",
        nature_light_appliance_name=light_name,
        nature_unlock_signals=unlock_signals,
        nature_lock_signals=lock_signals,
    )


def _appliances() -> tuple[NatureAppliance, ...]:
    return (
        NatureAppliance("light-id", "主照明", "LIGHT", ()),
        NatureAppliance(
            "tape-light-id",
            "間接照明",
            "IR",
            (
                NatureSignal("on-id", "オン"),
                NatureSignal("blue-id", "B"),
                NatureSignal("green-id", "G"),
            ),
        ),
    )


def test_get_appliances_uses_api_and_parses_names(monkeypatch) -> None:
    captured = {}
    response_body = json.dumps(
        [
            {
                "id": "light-id",
                "nickname": "主照明",
                "type": "LIGHT",
                "signals": [],
            },
            {
                "id": "tape-light-id",
                "nickname": "間接照明",
                "type": "IR",
                "signals": [{"id": "on-id", "name": "オン"}],
            },
        ]
    ).encode()

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["authorization"] = req.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse(response_body)

    monkeypatch.setattr(nature.request, "urlopen", fake_urlopen)

    appliances = NatureRemoClient("secret-token").get_appliances(timeout=3)

    assert captured == {
        "url": "https://api.nature.global/1/appliances",
        "method": "GET",
        "authorization": "Bearer secret-token",
        "timeout": 3,
    }
    assert appliances == (
        NatureAppliance("light-id", "主照明", "LIGHT", ()),
        NatureAppliance(
            "tape-light-id",
            "間接照明",
            "IR",
            (NatureSignal("on-id", "オン"),),
        ),
    )


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"{}",
        b'[{"id":"id","nickname":"name","type":"IR","signals":{}}]',
        b'[{"id":"id","nickname":"name","type":"IR","signals":[{}]}]',
    ],
)
def test_get_appliances_rejects_invalid_responses(monkeypatch, body: bytes) -> None:
    monkeypatch.setattr(
        nature.request, "urlopen", lambda _req, timeout: FakeResponse(body)
    )

    with pytest.raises(RuntimeError, match=r"Nature Remo API returned (an )?invalid"):
        NatureRemoClient("secret-token").get_appliances()


def test_get_appliances_reports_connection_failure(monkeypatch) -> None:
    def fail_urlopen(_req, timeout):
        raise nature.error.URLError("offline")

    monkeypatch.setattr(nature.request, "urlopen", fail_urlopen)

    with pytest.raises(RuntimeError, match="request failed: offline"):
        NatureRemoClient("secret-token").get_appliances()


def test_get_appliances_reports_timeout(monkeypatch) -> None:
    def fail_urlopen(_req, timeout):
        raise TimeoutError

    monkeypatch.setattr(nature.request, "urlopen", fail_urlopen)

    with pytest.raises(RuntimeError, match="request timed out"):
        NatureRemoClient("secret-token").get_appliances()


def test_resolve_nature_targets_preserves_signal_order() -> None:
    targets = resolve_nature_targets(_config(), _appliances())

    assert targets.light_appliance_id == "light-id"
    assert targets.unlock_signal_ids == ("on-id", "blue-id")
    assert targets.lock_signal_ids == ("on-id", "green-id")


@pytest.mark.parametrize(
    ("config", "appliances", "message"),
    [
        (_config(light_name="missing"), _appliances(), "LIGHT appliance not found"),
        (
            _config(),
            (
                NatureAppliance("other-id", "主照明", "IR", ()),
                _appliances()[1],
            ),
            "is not a LIGHT appliance",
        ),
        (
            _config(),
            (NatureAppliance("light-2", "主照明", "LIGHT", ()),) + _appliances(),
            "LIGHT appliance name is ambiguous",
        ),
        (
            _config(unlock_signals=(NatureSignalRef("間接照明", "missing"),)),
            _appliances(),
            "signal not found",
        ),
        (
            _config(unlock_signals=(NatureSignalRef("間接照明", "オン"),)),
            _appliances()
            + (
                NatureAppliance(
                    "duplicate",
                    "間接照明",
                    "IR",
                    (NatureSignal("duplicate-on", "オン"),),
                ),
            ),
            "signal name is ambiguous",
        ),
    ],
)
def test_resolve_nature_targets_rejects_missing_or_ambiguous_names(
    config: AppConfig,
    appliances: tuple[NatureAppliance, ...],
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        resolve_nature_targets(config, appliances)


def test_send_light_button_uses_light_appliance_api(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["authorization"] = req.get_header("Authorization")
        captured["content_type"] = req.get_header("Content-type")
        captured["data"] = req.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(nature.request, "urlopen", fake_urlopen)

    NatureRemoClient("secret-token").send_light_button("appliance-id", "on", timeout=3)

    assert captured == {
        "url": "https://api.nature.global/1/appliances/appliance-id/light",
        "authorization": "Bearer secret-token",
        "content_type": "application/x-www-form-urlencoded",
        "data": parse.urlencode({"button": "on"}).encode(),
        "timeout": 3,
    }


def test_send_signal_uses_signal_api(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["authorization"] = req.get_header("Authorization")
        captured["content_type"] = req.get_header("Content-type")
        captured["data"] = req.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(nature.request, "urlopen", fake_urlopen)

    NatureRemoClient("secret-token").send_signal("signal-id", timeout=4)

    assert captured == {
        "url": "https://api.nature.global/1/signals/signal-id/send",
        "method": "POST",
        "authorization": "Bearer secret-token",
        "content_type": None,
        "data": None,
        "timeout": 4,
    }
