# tests/test_scenarios.py
import pytest
import pandas as pd
from app.logic.scenarios import analyze_scenarios   # ✅ เปลี่ยน path

def _sample_df(n=80):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    base = pd.Series(range(n)) * 2 + 100
    df = pd.DataFrame({
        "timestamp": idx,
        "open": base,
        "high": base + 5,
        "low": base - 5,
        "close": base + (idx.day % 5),
        "volume": 1000,
    })
    return df

def test_scenarios_payload():
    df = _sample_df()
    payload = analyze_scenarios(df, symbol="BTCUSDT", tf="1D")
    assert "percent" in payload
    assert sum(payload["percent"].values()) == 100
    assert "levels" in payload
    assert "rationale" in payload
