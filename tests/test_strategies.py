# tests/test_strategies.py
import pytest
import pandas as pd

# ✅ เปลี่ยน import มาที่ logic
from app.logic.strategies import some_strategy_func


def _sample_df(n=100):
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


def test_strategy_output():
    df = _sample_df()
    out = some_strategy_func(df, symbol="TEST", tf="1D")
    assert isinstance(out, dict)
    assert "bias" in out
    assert out["bias"] in ("long", "short", "neutral")
