from __future__ import annotations

from typing import Dict, Tuple, Callable, Iterable
import pandas as pd

from .mtf_config import (
    TFS_DEFAULT, WEIGHTS, VOL_MIN, NEAR_EPS, MIN_BARS, TAIL
)

DataGetter = Callable[[str, str], pd.DataFrame]  # (symbol, tf) -> DataFrame

def _prep_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # EMA
    df["ema50"]  = df["close"].ewm(span=50,  adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    # RSI14 (EMA-style)
    delta = df["close"].diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = (avg_gain / (avg_loss.replace(0, 1e-12))).fillna(0)
    df["rsi14"] = 100 - (100 / (1 + rs))
    # ATR14 (% of close)
    prev_close = df["close"].shift(1)
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"]  - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(span=14, adjust=False).mean()
    df["atr_pct"] = (df["atr14"] / df["close"]).fillna(0)
    return df

def _classify_row(row: pd.Series, tf: str) -> str:
    ema_delta   = (row["ema50"] - row["ema200"]) / max(row["ema200"], 1e-12)
    up_regime   = ema_delta > 0
    down_regime = ema_delta < 0
    near_regime = abs(ema_delta) <= NEAR_EPS

    rsi    = float(row["rsi14"])
    vol_ok = float(row["atr_pct"]) >= VOL_MIN.get(tf, 0.002)

    # Minute TF policy:
    # - up_regime หรือ near_regime+RSI≥60 และมี vol_ok และ RSI≥55 → UP
    # - down_regime หรือ near_regime+RSI≤40 และมี vol_ok และ RSI≤45 → DOWN
    if vol_ok and ((up_regime) or (near_regime and rsi >= 60)) and rsi >= 55:
        return "UP"
    if vol_ok and ((down_regime) or (near_regime and rsi <= 40)) and rsi <= 45:
        return "DOWN"
    return "SIDE"

def analyze_tf(symbol: str, tf: str, data_getter: DataGetter, tail: int = TAIL) -> tuple[str, pd.Series]:
    df = data_getter(symbol, tf)
    if len(df) < MIN_BARS:
        raise ValueError(f"{tf}: data too short ({len(df)})")
    df = _prep_indicators(df.tail(tail))
    last = df.iloc[-1]
    signal = _classify_row(last, tf)
    return signal, last

def aggregate(signals: Dict[str, str]) -> Dict[str, float]:
    total_w = sum(WEIGHTS.values())
    up   = sum(WEIGHTS[tf] for tf, s in signals.items() if s == "UP")
    down = sum(WEIGHTS[tf] for tf, s in signals.items() if s == "DOWN")
    side = total_w - up - down
    return {
        "up_pct":   round(up   * 100 / total_w, 2),
        "down_pct": round(down * 100 / total_w, 2),
        "side_pct": round(side * 100 / total_w, 2),
    }

def analyze_mtf(
    symbol: str,
    tfs: Iterable[str] = TFS_DEFAULT,
    data_getter: DataGetter | None = None,
) -> tuple[str, Dict]:
    # default data_getter → ใช้ get_data ของโปรเจกต์
    if data_getter is None:
        from app.analysis.timeframes import get_data as _gd  # lazy import
        data_getter = _gd

    details: Dict[str, Dict] = {}
    signals: Dict[str, str] = {}

    for tf in tfs:
        sig, last = analyze_tf(symbol, tf, data_getter=data_getter)
        signals[tf] = sig
        details[tf] = {
            "time": str(last["timestamp"]),
            "close": float(last["close"]),
            "ema50": float(last["ema50"]),
            "ema200": float(last["ema200"]),
            "rsi14": float(last["rsi14"]),
            "atr_pct": float(last["atr_pct"]),
            "signal": sig,
            "weight": WEIGHTS.get(tf, 1),
        }

    agg = aggregate(signals)
    order = sorted(signals.keys(), key=lambda x: {"30M":0,"15M":1,"5M":2}.get(x, 99))
    seq = " / ".join(f"{tf}:{signals[tf]}" for tf in order)
    summary = (
        f"[MTF 5-15-30] {symbol} => {seq} "
        f"| Prob ≈ UP {agg['up_pct']}% / DOWN {agg['down_pct']}% / SIDE {agg['side_pct']}%"
    )

    payload = {"symbol": symbol, "signals": signals, "aggregate": agg, "details": details}
    return summary, payload

__all__ = ["analyze_mtf", "analyze_tf", "aggregate"]
