# PATCH: turn momentum_breakout into working scorer

from __future__ import annotations
from typing import Dict, Any, List, Optional, Literal
import math

try:
    from app.schemas.series import Series
except Exception:
    from typing import TypedDict
    class Candle(TypedDict, total=False):
        open: float; high: float; low: float; close: float
        volume: float; ts: int
    class Series(TypedDict):
        symbol: str
        timeframe: str
        candles: List[Candle]

from . import indicators as ind
from . import patterns as pat
from . import filters as flt

def _reason(code: str, message: str, weight: float, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "weight": float(weight), "meta": meta or {}}

def _to_df(series: Series):
    import pandas as pd
    df = pd.DataFrame(series.get("candles", []))
    for c in ("open","high","low","close","volume"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    if "ts" in df.columns:
        df = df.sort_values("ts")
    return df.dropna(subset=["open","high","low","close","volume"])

def _ema(s, n):
    import pandas as pd
    s = pd.to_numeric(s, errors="coerce")
    return s.ewm(span=n, adjust=False, min_periods=n).mean()

def _decide_bias(long_score: float, short_score: float, threshold: float = 0.6) -> Literal["long","short","neutral"]:
    if long_score >= threshold and long_score > short_score:
        return "long"
    if short_score >= threshold and short_score > long_score:
        return "short"
    return "neutral"

def momentum_breakout(series: Series, strategy_id: str = "momentum_breakout") -> Dict[str, Any]:
    reasons: List[Dict[str, Any]] = []
    long_score = 0.0
    short_score = 0.0

    # Filters
    if not flt.trend_filter(series):
        reasons.append(_reason("FILTER_TREND_FAIL", "trend ไม่ชัดพอ", 0.0))
        return {"symbol": series.get("symbol",""), "timeframe": series.get("timeframe",""),
                "long_score": 0.0, "short_score": 0.0, "bias": "neutral", "reasons": reasons, "strategy_id": strategy_id}
    if not flt.volatility_filter(series):
        reasons.append(_reason("FILTER_VOL_FAIL", "volatility ไม่พอ", 0.0))
        return {"symbol": series.get("symbol",""), "timeframe": series.get("timeframe",""),
                "long_score": 0.0, "short_score": 0.0, "bias": "neutral", "reasons": reasons, "strategy_id": strategy_id}
    # (session/volume optional)
    # if not flt.volume_filter(series, min_multiple_of_avg=1.0): ...

    # Patterns
    brk = pat.detect_breakout(series, lookback=20)
    if brk and brk.get("is_valid"):
        reasons.append(_reason("BRK_OK", f"breakout {brk['meta']['direction']}", 0.35, brk.get("meta")))
        if brk["meta"]["direction"] == "up":
            long_score += 0.35
        elif brk["meta"]["direction"] == "down":
            short_score += 0.35

    ib = pat.detect_inside_bar(series)
    if ib and ib.get("is_valid"):
        reasons.append(_reason("IB_OK", "inside bar (pre-breakout context)", 0.10, ib.get("meta")))
        # ให้โบนัสนิดหน่อยกับทิศทางตาม EMA โครงสร้าง
        pass

    # Indicators (จาก DataFrame ตรง ๆ)
    import pandas as pd
    df = _to_df(series)
    if len(df) >= 200:
        ema50 = _ema(df["close"], 50).iloc[-1]
        ema200 = _ema(df["close"], 200).iloc[-1]
        last = float(df["close"].iloc[-1])
        if not any(map(math.isnan, (ema50, ema200, last))):
            bull = last > ema200 and ema50 > ema200
            bear = last < ema200 and ema50 < ema200
            if bull:
                reasons.append(_reason("EMA_BULL", "EMA โครงสร้างขาขึ้น", 0.25, {"ema50": float(ema50), "ema200": float(ema200)}))
                long_score += 0.25
            elif bear:
                reasons.append(_reason("EMA_BEAR", "EMA โครงสร้างขาลง", 0.25, {"ema50": float(ema50), "ema200": float(ema200)}))
                short_score += 0.25

    # RSI / MACD แบบง่าย
    # ใช้ค่าเส้นสุดท้ายเพื่อชั่งน้ำหนัก
    close = pd.to_numeric(df["close"], errors="coerce")
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    gain = gain.shift(1).ewm(alpha=1/14, adjust=False).mean()
    loss = loss.shift(1).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss.replace(0, math.nan))
    rsi = 100 - (100 / (1 + rs))
    rsi_last = float(rsi.iloc[-1]) if not math.isnan(rsi.iloc[-1]) else None
    if rsi_last is not None:
        if rsi_last >= 55:
            reasons.append(_reason("RSI_GT55", f"RSI14 {rsi_last:.1f} bullish", 0.15, {"rsi14": rsi_last}))
            long_score += 0.15
        elif rsi_last <= 45:
            reasons.append(_reason("RSI_LT45", f"RSI14 {rsi_last:.1f} bearish", 0.15, {"rsi14": rsi_last}))
            short_score += 0.15

    # MACD histogram
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd_line = ema12 - ema26
    macd_sig  = macd_line.ewm(span=9, adjust=False, min_periods=9).mean()
    macd_hist = macd_line - macd_sig
    hist_last = float(macd_hist.iloc[-1]) if not math.isnan(macd_hist.iloc[-1]) else None
    if hist_last is not None:
        if hist_last > 0:
            reasons.append(_reason("MACD_POS", "MACD hist > 0", 0.15, {"hist": hist_last}))
            long_score += 0.15
        elif hist_last < 0:
            reasons.append(_reason("MACD_NEG", "MACD hist < 0", 0.15, {"hist": hist_last}))
            short_score += 0.15

    # Clamp 0..1
    long_score = max(0.0, min(1.0, long_score))
    short_score = max(0.0, min(1.0, short_score))
    bias = _decide_bias(long_score, short_score, threshold=0.6)

    return {
        "symbol": series.get("symbol", ""),
        "timeframe": series.get("timeframe", ""),
        "long_score": float(long_score),
        "short_score": float(short_score),
        "bias": bias,
        "reasons": reasons[:10],
        "strategy_id": strategy_id,
    }
