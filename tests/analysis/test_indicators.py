# tests/test_indicators.py
import pandas as pd
import numpy as np
from app.analysis import indicators as ind

def make_df(n=60):
    """สร้าง DataFrame ตัวอย่างสำหรับทดสอบ indicators"""
    rng = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "timestamp": rng,
        "open": np.linspace(100, 150, n),
        "high": np.linspace(101, 155, n),
        "low": np.linspace(99, 145, n),
        "close": np.linspace(100, 150, n) + np.random.randn(n),
        "volume": np.random.randint(100, 1000, n),
    })
    return df

def test_ema_basic():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    e = ind.ema(s, period=3)
    assert isinstance(e, pd.Series)
    assert len(e) == 10
    assert e.notna().sum() > 0

def test_rsi_within_bounds():
    df = make_df(100)
    r = ind.rsi(df["close"], 14)
    assert (r.dropna() >= 0).all()
    assert (r.dropna() <= 100).all()

def test_macd_returns_three_series():
    df = make_df(120)
    line, sig, hist = ind.macd(df["close"])
    assert isinstance(line, pd.Series)
    assert isinstance(sig, pd.Series)
    assert isinstance(hist, pd.Series)
    assert len(line) == len(sig) == len(hist) == len(df)

def test_adx_outputs_valid_range():
    df = make_df(120)
    adx, pdi, mdi = ind.adx(df["high"], df["low"], df["close"])
    assert (adx.dropna() >= 0).all()
    assert (pdi.dropna() >= 0).all()
    assert (mdi.dropna() >= 0).all()

def test_stoch_kd_in_range():
    df = make_df(120)
    k, d = ind.stoch_kd(df["high"], df["low"], df["close"])
    assert (k.dropna() >= 0).all() and (k.dropna() <= 100).all()
    assert (d.dropna() >= 0).all() and (d.dropna() <= 100).all()

def test_volume_metrics_returns_series():
    df = make_df(60)
    vol_ma, vol_z = ind.volume_metrics(df["volume"], window=20)
    assert isinstance(vol_ma, pd.Series)
    assert isinstance(vol_z, pd.Series)
    assert len(vol_ma) == len(vol_z) == len(df)

def test_apply_indicators_adds_columns():
    df = make_df(120)
    out = ind.apply_indicators(df)
    expected_cols = [
        "ema20","ema50","ema200",
        "rsi14",
        "macd","macd_signal","macd_hist",
        "adx14","plus_di14","minus_di14",
        "stoch_k","stoch_d",
        "vol_ma20","vol_z20"
    ]
    for col in expected_cols:
        assert col in out.columns
