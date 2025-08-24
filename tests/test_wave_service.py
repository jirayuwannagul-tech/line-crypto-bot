# tests/test_wave_service.py
import pytest
import pandas as pd
from app.services.wave_service import analyze_wave, build_brief_message

def test_analyze_wave_neutral_when_no_data(monkeypatch):
    # mock ให้ get_data คืน DataFrame ว่าง
    monkeypatch.setattr("app.services.wave_service.get_data", lambda *a, **kw: pd.DataFrame())

    payload = analyze_wave("BTCUSDT", "1D")
    assert "percent" in payload
    assert payload["percent"]["up"] + payload["percent"]["down"] + payload["percent"]["side"] == 100

def test_build_brief_message_safe():
    msg = build_brief_message({
        "symbol": "BTCUSDT",
        "tf": "1D",
        "percent": {"up": 40, "down": 35, "side": 25},
        "levels": {"recent_high": 120000, "recent_low": 110000, "ema50": 115000, "ema200": 100000},
        "last": {"close": 113000},
        "rationale": ["Dow UP", "RSI bullish"],
    })
    assert "BTCUSDT" in msg
    assert "ความน่าจะเป็น" in msg
