# tests/test_elliott.py
import pandas as pd
import pytest
from app.analysis import elliott

def test_analyze_elliott_basic():
    # mock ข้อมูลราคา
    data = {
        "open":  [100, 102, 105, 103, 108, 110, 107, 111],
        "high":  [102, 106, 107, 109, 112, 113, 111, 114],
        "low":   [99, 101, 103, 102, 106, 108, 106, 110],
        "close": [101, 105, 104, 108, 110, 109, 111, 113],
    }
    df = pd.DataFrame(data)

    result = elliott.analyze_elliott(df)

    # --- check structure ---
    assert isinstance(result, dict)
    for key in ["pattern", "completed", "current", "next", "targets"]:
        assert key in result

    # --- check data types ---
    assert isinstance(result["pattern"], str)
    assert isinstance(result["completed"], bool)
    assert isinstance(result["current"], dict)
    assert isinstance(result["next"], dict)
    assert isinstance(result["targets"], dict)
