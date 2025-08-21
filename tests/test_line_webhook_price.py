# tests/test_line_webhook_price.py
import sys, os
from fastapi.testclient import TestClient
import pytest

# ให้ import app ได้
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.main import app

client = TestClient(app)

def test_price_command_btc(monkeypatch):
    # --- 1) mock resolver ให้คืนราคาปลอม โดยรองรับทั้ง price/get/resolve ---
    from app.utils import crypto_price
    def _fake_price(symbol): return 12345.67

    if hasattr(crypto_price.resolver, "price"):
        monkeypatch.setattr(crypto_price.resolver, "price", _fake_price, raising=True)
    elif hasattr(crypto_price.resolver, "get"):
        monkeypatch.setattr(crypto_price.resolver, "get", _fake_price, raising=True)
    elif hasattr(crypto_price.resolver, "resolve"):
        monkeypatch.setattr(crypto_price.resolver, "resolve", _fake_price, raising=True)
    else:
        pytest.skip("resolver has no price/get/resolve method to mock")

    # --- 2) กันไม่ให้ยิง LINE จริง: mock line_bot_api.reply_message ---
    import app.routers.line_webhook as lw
    class _DummyLineAPI:
        def reply_message(self, *args, **kwargs):
            return None
    monkeypatch.setattr(lw, "line_bot_api", _DummyLineAPI(), raising=True)

    # --- 3) ยิง webhook ด้วยข้อความ 'ราคา BTC' ---
    payload = {
        "events": [{
            "replyToken": "TEST_REPLY_TOKEN",
            "type": "message",
            "timestamp": 1690000000000,
            "source": {"type": "user", "userId": "Uxxxxxxxxxxxxxx"},
            "message": {"id": "1", "type": "text", "text": "ราคา BTC"}
        }]
    }

    res = client.post("/line/webhook", json=payload)
    assert res.status_code == 200
    assert res.json().get("ok") is True
