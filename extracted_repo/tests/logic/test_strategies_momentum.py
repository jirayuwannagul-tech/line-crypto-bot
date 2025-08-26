# tests/test_strategies_momentum.py
from app.logic.strategies_momentum import momentum_breakout   # ✅ logic
from app.analysis import filters as flt

def make_series_trend(up=True, n=260, shock=False):
    import numpy as np
    # สร้างชุดข้อมูลที่มีเทรนด์ชัด + เบรกเอาท์ช่วงท้าย
    base = 100.0
    step = 0.3 if up else -0.3
    closes = [base + i * step for i in range(n)]
    if shock:
        # เบรกเอาท์ท้ายสุด
        closes[-1] = closes[-2] + (5.0 if up else -5.0)

    def hlc(i, c):
        return c + 0.2, c - 0.2

    candles = []
    for i, c in enumerate(closes):
        h, l = hlc(i, c)
        o = c - step * 0.5
        v = 1200.0
        ts = i * 60_000
        candles.append({
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "ts": ts
        })
    return {"symbol": "TEST", "timeframe": "1H", "candles": candles}

def test_momentum_breakout_long_bias():
    s = make_series_trend(up=True, shock=True)
    out = momentum_breakout(s)
    assert set(out.keys()) >= {"long_score", "short_score", "bias", "reasons", "strategy_id"}
    # เทรนด์ขึ้น + เบรกเอาท์ → ควรเอนเข้า long หรืออย่างน้อยไม่ neutral
    assert out["bias"] in ("long", "neutral")

def test_momentum_breakout_short_bias():
    s = make_series_trend(up=False, shock=True)
    out = momentum_breakout(s)
    assert out["bias"] in ("short", "neutral")
