# tests/test_elliott.py
import pytest
import pandas as pd
from app.analysis.elliott import analyze_elliott

def _zigzag_df():
    # fake zigzag: 100→200 (A), 200→150 (B), 150→250 (C)
    ts = pd.date_range("2024-01-01", periods=6, freq="D")
    df = pd.DataFrame({
        "timestamp": ts,
        "open": [100,200,150,250,240,245],
        "high": [200,210,160,255,245,250],
        "low":  [ 95,195,145,240,235,240],
        "close":[200,150,250,245,246,247],
        "volume": 1000,
    })
    return df

def test_elliott_basic():
    df = _zigzag_df()
    res = analyze_elliott(df)
    assert "pattern" in res
    assert res["pattern"] in ("IMPULSE","ZIGZAG","FLAT","TRIANGLE","UNKNOWN")
