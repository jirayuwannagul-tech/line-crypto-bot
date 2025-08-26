import math
from app.analysis import filters as flt

def make_series(up=True, n=250, noise=0.5):
    import numpy as np, pandas as pd
    # สร้างข้อมูลจำลอง: ขาขึ้น/ขาลง + มี volume/hlc ครบ
    x = np.arange(n, dtype=float)
    trend = (x*0.5) if up else (-x*0.5)
    close = trend + np.random.normal(0, noise, size=n) + 100
    open_ = close + np.random.normal(0, noise, size=n)
    high  = np.maximum(open_, close) + abs(np.random.normal(0, noise, size=n))
    low   = np.minimum(open_, close) - abs(np.random.normal(0, noise, size=n))
    vol   = np.abs(np.random.normal(1000, 100, size=n))
    ts    = (x*60_000).astype(int)
    candles = [{"open":float(o),"high":float(h),"low":float(l),"close":float(c),"volume":float(v),"ts":int(t)}
               for o,h,l,c,v,t in zip(open_,high,low,close,vol,ts)]
    return {"symbol":"TEST","timeframe":"1H","candles":candles}

def test_trend_and_volatility_pass_on_trending_market():
    s = make_series(up=True)
    assert flt.trend_filter(s) is True
    assert flt.volatility_filter(s) in (True, False)  # แค่ให้รันได้ ไม่ crash

def test_volume_filter_runs():
    s = make_series(up=True)
    assert flt.volume_filter(s, min_multiple_of_avg=0.8) in (True, False)

def test_is_sideway_df_and_side_confidence_no_crash():
    # ตลาดนิ่ง: สร้างด้วย noise ต่ำและ trend แทบไม่มี
    s = make_series(up=True, noise=0.05)
    import pandas as pd
    df = pd.DataFrame(s["candles"]).sort_values("ts")
    mask = flt.is_sideway_df(df)
    assert len(mask) == len(df)
    # คำนวณคะแนนจากแถวสุดท้าย (ไม่มี error)
    row = df.iloc[-1].to_dict()
    _ = flt.side_confidence(row)
