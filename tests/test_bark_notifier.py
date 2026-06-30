import json

from util.notifer.BarkUtil import BarkNotifier


class _FakeResponse:
    def __init__(self):
        self.raise_called = False

    def raise_for_status(self):
        self.raise_called = True


def test_bark_notifier_checks_response_status(monkeypatch):
    captured = {}
    response = _FakeResponse()

    def fake_post(url, *, headers, data, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = json.loads(data)
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr("util.notifer.BarkUtil.requests.post", fake_post)

    BarkNotifier(
        token="https://bark.example.test/device-key",
        title="抢票成功",
        content="content",
    ).send_message("抢票成功", "message")

    assert captured["url"] == "https://bark.example.test/device-key/抢票成功/message"
    assert captured["headers"] == {"Content-Type": "application/json"}
    assert captured["timeout"] == 10
    assert captured["data"]["group"] == "biliTickerBuy"
    assert response.raise_called is True
