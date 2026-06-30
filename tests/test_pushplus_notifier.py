import pytest

from util.proxy.PushPlusUtil import PushPlusNotifier


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_called = False

    def raise_for_status(self):
        self.raise_called = True

    def json(self):
        return self.payload


def test_pushplus_notifier_sends_json_and_checks_response(monkeypatch):
    captured = {}
    response = _FakeResponse({"code": 200, "msg": "执行成功"})

    def fake_post(url, *, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr("util.proxy.PushPlusUtil.requests.post", fake_post)

    PushPlusNotifier(token="token-value", title="t", content="c").send_message(
        "抢票成功",
        "message",
    )

    assert captured["url"] == "https://www.pushplus.plus/send"
    assert captured["json"] == {
        "token": "token-value",
        "content": "message",
        "title": "抢票成功",
    }
    assert captured["timeout"] == 10
    assert response.raise_called is True


def test_pushplus_notifier_raises_on_business_error(monkeypatch):
    def fake_post(url, *, json, timeout):
        return _FakeResponse({"code": 999, "msg": "token不能为空"})

    monkeypatch.setattr("util.proxy.PushPlusUtil.requests.post", fake_post)

    with pytest.raises(RuntimeError, match="token不能为空"):
        PushPlusNotifier(token="token-value", title="t", content="c").send_message(
            "抢票成功",
            "message",
        )
