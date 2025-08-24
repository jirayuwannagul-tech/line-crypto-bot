# tests/test_dow.py
import pytest
import pandas as pd
from app.analysis.dow import analyze_dow
from app.analysis.indicators import apply_indicators

def _make_trend_df(up=True, n=60):
    # synthetic trend data
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    if up:
        base = pd.Series(range(n)) * 10 + 100
    else:
        base = pd.Series(range(n))[::-1] * 10 + 100
    df = pd.DataFrame({
        "timestamp": idx,
        "open": base,
        "high": base + 5,
        "low": base - 5,
        "close": base,
        "volume": 1000,
    })
    return apply_indicators(df)

def test_dow_uptrend():
    df = _make_trend_df(up=True)
    res = analyze_dow(df)
    assert res["trend_primary"] in ("UP", "SIDE")

def test_dow_downtrend():
    df = _make_trend_df(up=False)
    res = analyze_dow(df)
    assert res["trend_primary"] in ("DOWN", "SIDE")
