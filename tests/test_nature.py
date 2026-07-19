from urllib import parse

from sesame_remo import nature
from sesame_remo.nature import NatureRemoClient


class FakeResponse:
    status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


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
