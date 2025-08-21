# tests/test_line_webhook_price.py
import sys, os
import pytest
from fastapi.testclient import TestClient

# เพิ่ม path root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app

client = TestClient(app)

def test_price_command_btc(monkeypatch):
    # mock resolver ให้คืนราคาปลอม
    from app.utils import crypto_price
    monkeypatch.setattr(crypto_price.resolver, "price", lambda symbol: 12345.67)

    payload = {
        "events": [{
            "replyToken": "TEST_REPLY_TOKEN",
            "type": "message",
            "timestamp": 1690000000000,
            "source": { "type": "user", "userId": "Uxxxxxxxxxxxxxx" },
            "message": { "id": "1", "type": "text", "text": "ราคา BTC" }
        }]
    }

    res = client.post("/line/webhook", json=payload)
    assert res.status_code == 200
    assert res.json()["ok"] is True
