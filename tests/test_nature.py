from urllib import parse

from sesame_remo import nature
from sesame_remo.nature import NatureRemoClient


class FakeResponse:
    status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_send_light_on_uses_light_appliance_api(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["authorization"] = req.get_header("Authorization")
        captured["content_type"] = req.get_header("Content-type")
        captured["data"] = req.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(nature.request, "urlopen", fake_urlopen)

    NatureRemoClient("secret-token", "appliance-id", "on").send_light_on(timeout=3)

    assert captured == {
        "url": "https://api.nature.global/1/appliances/appliance-id/light",
        "authorization": "Bearer secret-token",
        "content_type": "application/x-www-form-urlencoded",
        "data": parse.urlencode({"button": "on"}).encode(),
        "timeout": 3,
    }
