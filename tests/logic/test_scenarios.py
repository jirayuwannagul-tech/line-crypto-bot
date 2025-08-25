# tests/logic/test_scenarios.py
def test_softmax_sum_100(monkeypatch):
    import pandas as pd, numpy as np, datetime as dt
    from app.logic.scenarios import analyze_scenarios
    import app.logic.scenarios as sc

    # -- fake indicators: เติมคอลัมน์ที่จำเป็นให้ครบ
    def _fake_apply_indicators(df, *_args, **_kwargs):
        df = df.copy()
        df["ema50"] = df["close"].rolling(5, min_periods=1).mean()
        df["ema200"] = df["close"].rolling(10, min_periods=1).mean()
        df["rsi14"] = 50.0
        df["macd_hist"] = 0.0
        return df

    # -- fake elliott: คงที่/เป็นกลาง
    def _fake_classify_elliott(df, timeframe="1D", weekly_det=None):
        return {"pattern": "UNKNOWN", "kind": "UNKNOWN", "current": {"direction": "side"}}

    monkeypatch.setattr(sc, "apply_indicators", _fake_apply_indicators)
    monkeypatch.setattr(sc, "classify_elliott_with_kind", _fake_classify_elliott)

    # สร้าง df พื้นฐาน
    idx = pd.date_range(end=dt.datetime(2025, 8, 25), periods=60, freq="D")
    df = pd.DataFrame({
        "timestamp": idx,
        "open":  np.linspace(100, 110, len(idx)),
        "high":  np.linspace(101, 111, len(idx)),
        "low":   np.linspace( 99, 109, len(idx)),
        "close": np.linspace(100, 110, len(idx)),
        "volume": np.linspace(1000, 2000, len(idx)),
    })

    payload = analyze_scenarios(df, symbol="BTCUSDT", tf="1D", cfg={"profile": "baseline"})
    total = sum(payload["percent"].values())
    assert total == 100, f"sum={total}, payload={payload['percent']}"
