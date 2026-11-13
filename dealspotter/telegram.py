"""Send a message through the Telegram Bot API (injectable HTTP)."""
from __future__ import annotations

import json
import urllib.request


def default_post(url: str, body: dict) -> dict:  # pragma: no cover - needs network
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def make_sender(token: str, chat_id: str, post=default_post):
    def send(text: str) -> None:
        resp = post(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat_id, "text": text})
        if not resp.get("ok"):
            raise RuntimeError("Telegram did not accept the message")

    return send
