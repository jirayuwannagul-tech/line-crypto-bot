# app/analysis/scenarios.py
# -----------------------------------------------------------------------------
# Combine Dow + Elliott + Fibonacci + Indicators into a unified scenario score.
# Returns %up / %down / %side (sum=100) with key levels & short rationale.
#
# Public API:
#   analyze_scenarios(df: pd.DataFrame, symbol="BTCUSDT", tf="1D", cfg=None) -> Dict
#
# Notes:
# - Self‑contained: computes indicators internally, then calls Dow/Elliott.
# - Uses simple votes -> softmax to form probabilities (robust & explainable).
# - Key levels: recent swing high/low, EMA(50/200), Fibonacci from last leg,
#   plus Elliott targets if any.
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import math
import numpy as np
import pandas as pd

from .indicators import apply_indicators
from .dow import analyze_dow
from .fibonacci import fib_levels, fib_extensions
from . import elliott as ew  # use analyze_elliott

__all__ = ["analyze_scenarios"]

# -----------------------------------------------------------------------------
# Internal utilities
# -----------------------------------------------------------------------------

def _fractals(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[pd.Series, pd.Series]:
    """Return boolean Series for swing high / swing low."""
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        win_h = high[i-left:i+right+1]
        win_l = low[i-left:i+right+1]
        if np.argmax(win_h) == left and high[i] == win_h.max():
            sh[i] = True
        if np.argmin(win_l) == left and low[i] == win_l.min():
            sl[i] = True
    return pd.Series(sh, index=df.index), pd.Series(sl, index=df.index)


def _recent_swings(df: pd.DataFrame, k: int = 5) -> Dict[str, float]:
    """Get recent swing high/low and most recent leg direction A->B (A,B prices)."""
    is_sh, is_sl = _fractals(df)
    sw_rows: List[Tuple[int, str, float]] = []
    for i in range(len(df)):
        if is_sh.iat[i]:
            sw_rows.append((i, "H", float(df["high"].iat[i])))
        if is_sl.iat[i]:
            sw_rows.append((i, "L", float(df["low"].iat[i])))
    if not sw_rows:
        return {}
    sw_rows.sort(key=lambda x: x[0])
    sw_rows = sw_rows[-max(2, k):]  # keep last swings

    last_type = sw_rows[-1][1]
    last_price = sw_rows[-1][2]
    # determine previous opposite swing for last leg
    prev = None
    for j in range(len(sw_rows)-2, -1, -1):
        if sw_rows[j][1] != last_type:
            prev = sw_rows[j]
            break
    out = {
        "last_swing_type": last_type,
        "last_swing_price": last_price,
        "recent_high": max(p for _, t, p in sw_rows if t == "H") if any(t=="H" for _,t,_ in sw_rows) else float(df["high"].tail(20).max()),
        "recent_low":  min(p for _, t, p in sw_rows if t == "L") if any(t=="L" for _,t,_ in sw_rows) else float(df["low"].tail(20).min()),
    }
    if prev is not None:
        out["prev_swing_type"] = prev[1]
        out["prev_swing_price"] = prev[2]
        out["leg_A"] = prev[2]
        out["leg_B"] = last_price
        out["leg_dir"] = "up" if last_price > prev[2] else "down" if last_price < prev[2] else "side"
    return out


def _softmax3(u: float, d: float, s: float) -> Tuple[float, float, float]:
    """Numerically stable softmax for 3 logits → probabilities (0..1)."""
    arr = np.array([u, d, s], dtype=float)
    m = np.max(arr)
    e = np.exp(arr - m)
    p = e / e.sum()
    return float(p[0]), float(p[1]), float(p[2])


def _pct(x: float) -> int:
    return int(round(100 * x))


# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------

def analyze_scenarios(
    df: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    Combine Dow + Elliott + Fibo + Indicators and output % probabilities + levels.

    Input df columns required:
      timestamp, open, high, low, close, volume
    """
    cfg = cfg or {}
    if len(df) < 50:
        return {
            "percent": {"up": 33, "down": 33, "side": 34},
            "levels": {},
            "rationale": ["Data too short, returning neutral probabilities."],
            "meta": {"symbol": symbol, "tf": tf},
        }

    # 1) Indicators
    df_ind = apply_indicators(df, cfg.get("ind_cfg", None))
    last = df_ind.iloc[-1]

    # 2) Dow & Elliott
    dow = analyze_dow(df_ind)
    ell = ew.analyze_elliott(df_ind, pivot_left=cfg.get("pivot_left", 2), pivot_right=cfg.get("pivot_right", 2))

    # 3) Swings & Fibo (from last leg)
    sw_meta = _recent_swings(df_ind, k=7)
    fibo_levels = {}
    if "leg_A" in sw_meta and "leg_B" in sw_meta and sw_meta.get("leg_dir") in ("up", "down"):
        A = sw_meta["leg_A"]
        B = sw_meta["leg_B"]
        retr = fib_levels(A, B)["levels"]
        exts = fib_extensions(A, B)["levels"]
        # keep common keys
        fibo_levels = {
            "retr_0.382": retr.get("0.382"),
            "retr_0.5": retr.get("0.5"),
            "retr_0.618": retr.get("0.618"),
            "ext_1.272": exts.get("1.272"),
            "ext_1.618": exts.get("1.618"),
        }

    # 4) Voting logic → logits (not yet normalized)
    up_logit = 0.0
    down_logit = 0.0
    side_logit = 0.0
    notes: List[str] = []

    # Dow primary
    dp = dow.get("trend_primary", "SIDE")
    dc = int(dow.get("confidence", 50))
    if dp == "UP":
        w = 1.0 + (dc - 50) / 100.0  # 0.5..1.5 approx
        up_logit += 1.8 * w
        notes.append(f"Dow primary UP (confidence={dc}).")
    elif dp == "DOWN":
        w = 1.0 + (dc - 50) / 100.0
        down_logit += 1.8 * w
        notes.append(f"Dow primary DOWN (confidence={dc}).")
    else:
        side_logit += 0.8
        notes.append("Dow primary SIDE.")

    # Elliott pattern bias
    patt = ell.get("pattern", "UNKNOWN")
    edir = (ell.get("current", {}) or {}).get("direction", "side")
    # Heuristic mapping:
    if patt in ("IMPULSE", "DIAGONAL"):
        # trend continuation bias in current direction
        if edir == "up":
            up_logit += 1.4
            notes.append(f"Elliott {patt} bias UP.")
        elif edir == "down":
            down_logit += 1.4
            notes.append(f"Elliott {patt} bias DOWN.")
    elif patt in ("ZIGZAG", "FLAT", "TRIANGLE"):
        # corrective completed → bias opposite next_stage clue
        nxt = (ell.get("next", {}) or {}).get("stage", "")
        if "resume_trend_up" in nxt or "thrust_up" in nxt:
            up_logit += 1.2
            notes.append(f"Elliott {patt} suggests UP next.")
        elif "resume_trend_down" in nxt or "thrust_down" in nxt:
            down_logit += 1.2
            notes.append(f"Elliott {patt} suggests DOWN next.")
        else:
            side_logit += 0.6
            notes.append(f"Elliott {patt} unclear, SIDE bias.")
    else:
        side_logit += 0.4
        notes.append("Elliott UNKNOWN.")

    # Indicators bias
    # RSI bands
    rsi = float(last.get("rsi14", np.nan))
    if not math.isnan(rsi):
        if rsi >= 55:
            up_logit += 0.8; notes.append(f"RSI14 {rsi:.1f} (>55) bullish.")
        elif rsi <= 45:
            down_logit += 0.8; notes.append(f"RSI14 {rsi:.1f} (<45) bearish.")
        else:
            side_logit += 0.3; notes.append(f"RSI14 {rsi:.1f} neutral.")
    # MACD hist
    macd_hist = float(last.get("macd_hist", np.nan))
    if not math.isnan(macd_hist):
        if macd_hist > 0:
            up_logit += 0.6; notes.append("MACD histogram > 0.")
        elif macd_hist < 0:
            down_logit += 0.6; notes.append("MACD histogram < 0.")

    # EMA structure
    ema50 = float(last.get("ema50", np.nan))
    ema200 = float(last.get("ema200", np.nan))
    close = float(last.get("close", np.nan))
    if not any(math.isnan(x) for x in (ema50, ema200, close)):
        if close > ema200 and ema50 > ema200:
            up_logit += 0.9; notes.append("Price & EMA50 above EMA200 (bull structure).")
        elif close < ema200 and ema50 < ema200:
            down_logit += 0.9; notes.append("Price & EMA50 below EMA200 (bear structure).")
        else:
            side_logit += 0.4; notes.append("Mixed EMA structure.")

    # ADX trend strength (amplify trend side)
    adx14 = float(last.get("adx14", np.nan))
    if not math.isnan(adx14) and adx14 >= 20:
        if up_logit > down_logit and dp == "UP":
            up_logit += 0.4; notes.append(f"ADX14 {adx14:.1f} supports UP trend.")
        elif down_logit > up_logit and dp == "DOWN":
            down_logit += 0.4; notes.append(f"ADX14 {adx14:.1f} supports DOWN trend.")
        else:
            side_logit += 0.2; notes.append(f"ADX14 {adx14:.1f} trend present but mixed.")

    # Sideways check (range compression)
    rng = float(df_ind["high"].tail(20).max() - df_ind["low"].tail(20).min())
    lvl = close if not math.isnan(close) else 0.0
    if lvl > 0 and rng / lvl < 0.035:
        side_logit += 0.8; notes.append("20-bar range < 3.5% → SIDE bias.")

    # 5) Convert to probabilities
    pu, pd, ps = _softmax3(up_logit, down_logit, side_logit)

    # 6) Key levels
    levels = {
        "recent_high": sw_meta.get("recent_high"),
        "recent_low": sw_meta.get("recent_low"),
        "ema50": ema50 if not math.isnan(ema50) else None,
        "ema200": ema200 if not math.isnan(ema200) else None,
        "fibo": fibo_levels,
        "elliott_targets": ell.get("targets", {}),
    }

    # 7) Compose payload
    payload = {
        "percent": {"up": _pct(pu), "down": _pct(pd), "side": _pct(ps)},
        "levels": levels,
        "rationale": notes[:10],  # keep it short
        "meta": {
            "symbol": symbol,
            "tf": tf,
            "dow": dow,
            "elliott": {k: v for k, v in ell.items() if k != "debug"},
            "swings": {k: v for k, v in sw_meta.items() if k in ("last_swing_type","last_swing_price","prev_swing_type","prev_swing_price","leg_dir")},
        },
    }
    # enforce sum=100 (adjust side)
    total = payload["percent"]["up"] + payload["percent"]["down"] + payload["percent"]["side"]
    if total != 100:
        diff = 100 - total
        payload["percent"]["side"] = max(0, min(100, payload["percent"]["side"] + diff))
    return payload
