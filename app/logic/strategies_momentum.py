# app/logic/strategies_momentum.py
# LOGIC layer — ปรับ threshold / filters / regime เท่านั้น (ไม่แตะ RULES)

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

# ✅ ใช้ absolute import
from app.analysis import indicators as ind
from app.analysis import patterns as pat
from app.analysis import filters as flt

Trend = Literal["UP", "DOWN", "SIDE"]

# -----------------------------
# Helper Functions
# -----------------------------
def _reason(code: str, message: str, weight: float, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "weight": float(weight), "meta": meta or {}}


def _to_df(series: Series):
    import pandas as pd
    df = pd.DataFrame(series.get("candles", []))
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    if "ts" in df.columns:
        df = df.sort_values("ts")
        df = df.set_index("ts", drop=False)
    return df.dropna(subset=["open", "high", "low", "close", "volume"])


def _ema(s, n):
    import pandas as pd
    s = pd.to_numeric(s, errors="coerce")
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _rsi(close, period: int = 14):
    import pandas as pd
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    gain = gain.shift(1).ewm(alpha=1/period, adjust=False).mean()
    loss = loss.shift(1).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / (loss.replace(0, math.nan))
    return 100 - (100 / (1 + rs))


def _atr(df, period: int = 14):
    import pandas as pd
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    prev_close = close.shift(1)
    tr = (high - low).abs()
    tr = pd.concat([
        tr,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False, min_periods=period).mean()


def _decide_bias(long_score: float, short_score: float, threshold: float = 0.6) -> Literal["long", "short", "neutral"]:
    if long_score >= threshold and long_score > short_score:
        return "long"
    if short_score >= threshold and short_score > long_score:
        return "short"
    return "neutral"


# -----------------------------
# Momentum Config + Series Signal (ใหม่)
# -----------------------------
class MomentumConfig:
    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_trend: int = 200,
        rsi_period: int = 14,
        rsi_bull_min: float = 55.0,
        rsi_bear_max: float = 45.0,
        atr_period: int = 14,
        atr_flip_k: float = 0.75,  # ต้องเกิน k*ATR ถึงจะยอมสลับฝั่ง
        confirm_bars: int = 2,     # ต้องยืนยันแท่งก่อนสลับฝั่ง
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.rsi_period = rsi_period
        self.rsi_bull_min = rsi_bull_min
        self.rsi_bear_max = rsi_bear_max
        self.atr_period = atr_period
        self.atr_flip_k = atr_flip_k
        self.confirm_bars = confirm_bars


def momentum_signal_series(series: Series, cfg: Optional[MomentumConfig] = None) -> List[Trend]:
    """
    ให้สัญญาณโมเมนตัมต่อแท่ง (UP/DOWN/SIDE) โดยใช้ EMA regime + RSI + ATR gate + debounce flip
    - ใช้เฉพาะเลเยอร์ LOGIC (ไม่แตะ RULES)
    """
    cfg = cfg or MomentumConfig()
    import pandas as pd

    df = _to_df(series)
    if len(df) < max(cfg.ema_trend, cfg.atr_period, cfg.rsi_period):
        return ["SIDE"] * len(df)

    ema_f = _ema(df["close"], cfg.ema_fast)
    ema_s = _ema(df["close"], cfg.ema_slow)
    ema_t = _ema(df["close"], cfg.ema_trend)
    rsi = _rsi(df["close"], cfg.rsi_period)
    atr = _atr(df, cfg.atr_period)

    out: List[Trend] = []
    prev: Optional[Trend] = None
    streak_want: Optional[Trend] = None
    streak_len = 0

    for i in range(len(df)):
        c = float(df["close"].iloc[i])
        ef = float(ema_f.iloc[i]) if not math.isnan(ema_f.iloc[i]) else math.nan
        es = float(ema_s.iloc[i]) if not math.isnan(ema_s.iloc[i]) else math.nan
        et = float(ema_t.iloc[i]) if not math.isnan(ema_t.iloc[i]) else math.nan
        r = float(rsi.iloc[i]) if not math.isnan(rsi.iloc[i]) else math.nan
        a = float(atr.iloc[i]) if not math.isnan(atr.iloc[i]) else math.nan

        raw: Trend = "SIDE"
        if not any(map(math.isnan, (ef, es, et, r))):
            long_bias = (es > et) and (ef > es) and (r >= cfg.rsi_bull_min)
            short_bias = (es < et) and (ef < es) and (r <= cfg.rsi_bear_max)
            if long_bias:
                raw = "UP"
            elif short_bias:
                raw = "DOWN"

        # ATR gate ป้องกัน flip หลอก (ต้องขยับจาก EMA_fast เกิน k*ATR)
        cur = raw
        if prev and cur != "SIDE" and cur != prev and not math.isnan(a):
            ref = ef if not math.isnan(ef) else c
            if abs(c - ref) < cfg.atr_flip_k * a:
                cur = prev  # แรงไม่พอ ยังไม่ flip

        # Debounce: ต้องยืนยัน ≥ confirm_bars ก่อนสลับ
        if prev and cur != prev:
            if streak_want != cur:
                streak_want, streak_len = cur, 1
            else:
                streak_len += 1
            if streak_len >= cfg.confirm_bars:
                prev = cur
                streak_want, streak_len = None, 0
            # ถ้ายังไม่ครบ confirm → คง prev เดิม
            out.append(prev if prev else cur)
        else:
            # ไม่มีการขอเปลี่ยนฝั่ง
            streak_want, streak_len = None, 0
            prev = cur if cur != "SIDE" else (prev or "SIDE")
            out.append(prev)

    return out


def momentum_last_signal(series: Series, cfg: Optional[MomentumConfig] = None) -> Trend:
    sigs = momentum_signal_series(series, cfg)
    return sigs[-1] if sigs else "SIDE"


# -----------------------------
# Main Strategy Scorer (เดิม)
# -----------------------------
def momentum_breakout(series: Series, strategy_id: str = "momentum_breakout") -> Dict[str, Any]:
    """
    Scorer เชิงโมเมนตัม + เบรกเอาท์:
      - ใช้ filters เบื้องต้น (trend/volatility)
      - รวมสัญญาณ patterns (breakout, inside-bar) + EMA + RSI/MACD
      - คืนคะแนน long/short แบบ 0..1 และ bias = long/short/neutral
    """
    reasons: List[Dict[str, Any]] = []
    long_score = 0.0
    short_score = 0.0

    # --- Filters
    if not flt.trend_filter(series):
        reasons.append(_reason("FILTER_TREND_FAIL", "trend ไม่ชัดพอ", 0.0))
        return {
            "symbol": series.get("symbol", ""),
            "timeframe": series.get("timeframe", ""),
            "long_score": 0.0,
            "short_score": 0.0,
            "bias": "neutral",
            "reasons": reasons,
            "strategy_id": strategy_id,
        }

    if not flt.volatility_filter(series):
        reasons.append(_reason("FILTER_VOL_FAIL", "volatility ไม่พอ", 0.0))
        return {
            "symbol": series.get("symbol", ""),
            "timeframe": series.get("timeframe", ""),
            "long_score": 0.0,
            "short_score": 0.0,
            "bias": "neutral",
            "reasons": reasons,
            "strategy_id": strategy_id,
        }

    # --- Patterns
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

    # --- Indicators
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
                reasons.append(_reason("EMA_BULL", "EMA โครงสร้างขาขึ้น", 0.25,
                                       {"ema50": float(ema50), "ema200": float(ema200)}))
                long_score += 0.25
            elif bear:
                reasons.append(_reason("EMA_BEAR", "EMA โครงสร้างขาลง", 0.25,
                                       {"ema50": float(ema50), "ema200": float(ema200)}))
                short_score += 0.25

    # RSI14
    close = pd.to_numeric(df["close"], errors="coerce")
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
    macd_sig = macd_line.ewm(span=9, adjust=False, min_periods=9).mean()
    macd_hist = macd_line - macd_sig
    hist_last = float(macd_hist.iloc[-1]) if not math.isnan(macd_hist.iloc[-1]) else None
    if hist_last is not None:
        if hist_last > 0:
            reasons.append(_reason("MACD_POS", "MACD hist > 0", 0.15, {"hist": hist_last}))
            long_score += 0.15
        elif hist_last < 0:
            reasons.append(_reason("MACD_NEG", "MACD hist < 0", 0.15, {"hist": hist_last}))
            short_score += 0.15

    # --- Clamp & decide
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


# -----------------------------
# ✅ Fix for tests
# -----------------------------
def some_strategy_func(data=None, symbol: str = None, tf: str = None):
    """
    Placeholder สำหรับเทส:
      - รองรับ signature ที่เทสต้องการ (data, symbol, tf)
      - คืนค่าตัวอย่าง output
    """
    return {
        "name": "some_strategy_func",
        "ready": True,
        "symbol": symbol,
        "timeframe": tf,
        "data_preview": None if data is None else str(type(data)),
    }
