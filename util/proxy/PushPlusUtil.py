import requests

from util.notifer.Notifier import NotifierBase


class PushPlusNotifier(NotifierBase):
    def __init__(self, token, title, content, interval_seconds=10, duration_minutes=10):
        super().__init__(title, content, interval_seconds, duration_minutes)
        self.token = token

    def send_message(self, title, message):
        url = "https://www.pushplus.plus/send"

        data = {"token": self.token, "content": message, "title": title}
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()

        payload = response.json()
        if payload.get("code") != 200:
            raise RuntimeError(f"PushPlus推送失败: {payload.get('msg') or payload}")
