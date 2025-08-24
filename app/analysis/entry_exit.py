# app/analysis/entry_exit.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# - สร้างคำแนะนำ Entry/SL/TP โดยยึด Elliott เป็นแกน ผ่านผลจาก scenarios()
# - รองรับ "โปรไฟล์" (baseline / cholak / chinchot) ที่มากำหนดเกณฑ์ยืนยันสัญญาณ
#   และรูปแบบการตั้งเป้าหมายราคา (Fibonacci / เปอร์เซ็นต์)
# =============================================================================

from __future__ import annotations
from typing import Dict, Optional, Tuple, List
import os
import math
import pandas as pd

# ✅ FIX IMPORT: ใช้ absolute import ป้องกัน ModuleNotFoundError
from app.analysis.scenarios import analyze_scenarios
from app.analysis.indicators import apply_indicators

__all__ = ["suggest_trade", "format_trade_text"]

# =============================================================================
# LAYER B) SMALL HELPERS
# -----------------------------------------------------------------------------
def _rr(entry: float, sl: float, tp: float) -> Optional[float]:
    if entry is None or sl is None or tp is None:
        return None
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    return None if risk == 0 else reward / risk

def _fmt(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    return f"{x:,.2f}"

def _safe_load_yaml(path: str) -> Optional[Dict]:
    try:
        import yaml
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        return None
    return None

_DEFAULTS = {
    "min_prob": 50,
    "min_rr": 1.30,
    "use_pct_targets": False,
    "sl_pct": 0.03,
    "tp_pcts": [0.03, 0.07, 0.12],
    "confirm": {
        "rsi_bull_min": 55,
        "rsi_bear_max": 45,
        "ema_structure_required": False,
        "atr_min_pct": 0.004,
    },
    "fibo": {
        "retr": [0.382, 0.5, 0.618],
        "ext": [1.272, 1.618, 2.0],
        "cluster_tolerance": 0.0035,
    },
}

def _merge(a: Dict, b: Dict) -> Dict:
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out

def _get_profile(tf: str, name: str = "baseline") -> Dict:
    y = _safe_load_yaml(os.getenv("STRATEGY_PROFILES_PATH", "app/config/strategy_profiles.yaml")) or {}
    defaults = y.get("defaults", {}) if isinstance(y, dict) else {}
    profiles = y.get("profiles", {}) if isinstance(y, dict) else {}

    base = _merge(_DEFAULTS, defaults)
    prof = profiles.get(name, {}) if isinstance(profiles, dict) else {}
    merged = _merge(base, prof)

    ov = (prof.get("overrides", {}) or {}).get("by_timeframe", {}) if isinstance(prof, dict) else {}
    if tf in ov:
        merged = _merge(merged, ov[tf])
    return merged

def _atr_pct(df: pd.DataFrame, n: int = 14) -> Optional[float]:
    import numpy as np
    if len(df) < n + 1:
        return None
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    last_close = float(c.iloc[-1])
    return None if last_close == 0 or math.isnan(last_close) else float(atr.iloc[-1] / last_close)

# =============================================================================
# LAYER C) CORE LOGIC
# -----------------------------------------------------------------------------
def suggest_trade(
    df: Optional[pd.DataFrame],
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    cfg = cfg or {}

    if df is None:
        try:
            from app.analysis.timeframes import get_data
            df = get_data(symbol, tf, xlsx_path=cfg.get("xlsx_path"))
        except Exception as e:
            raise RuntimeError(f"cannot load dataframe for {symbol} {tf}: {e}")

    profile_name = str(cfg.get("profile", "baseline"))
    prof = _get_profile(tf, profile_name)

    sc = analyze_scenarios(df, symbol=symbol, tf=tf, cfg={"profile": profile_name, **cfg})
    df_ind = apply_indicators(df, cfg.get("ind_cfg"))
    last = df_ind.iloc[-1]
    close = float(last["close"])
    ema50 = float(last.get("ema50"))
    ema200 = float(last.get("ema200"))
    rsi14 = float(last.get("rsi14"))
    atrp = _atr_pct(df_ind, n=int(cfg.get("atr_period", 14)))

    perc: Dict[str, int] = sc.get("percent", {"up": 33, "down": 33, "side": 34})
    direction = max(perc, key=perc.get)
    min_prob = float(prof.get("min_prob", 0))
    notes: List[str] = []

    if perc.get(direction, 0) < min_prob:
        notes.append(f"Confidence below threshold: {perc.get(direction, 0)}% < {min_prob}%")

    levels = sc.get("levels", {}) or {}
    recent_high = levels.get("recent_high")
    recent_low = levels.get("recent_low")
    fibo = levels.get("fibo", {}) or {}
    ext_1272 = fibo.get("ext_1.272")
    ext_1618 = fibo.get("ext_1.618")
    ext_20 = fibo.get("ext_2.0")
    fib_cluster = levels.get("fib_cluster")

    rsi_ok = ema_ok = atr_ok = True
    rsi_bull_min = float(prof["confirm"]["rsi_bull_min"])
    rsi_bear_max = float(prof["confirm"]["rsi_bear_max"])
    ema_required = bool(prof["confirm"]["ema_structure_required"])
    atr_min_pct = float(prof["confirm"]["atr_min_pct"])

    if direction == "up":
        rsi_ok = rsi14 >= rsi_bull_min
        ema_ok = (close > ema200 and ema50 > ema200) if ema_required else True
    elif direction == "down":
        rsi_ok = rsi14 <= rsi_bear_max
        ema_ok = (close < ema200 and ema50 < ema200) if ema_required else True
    else:
        rsi_ok = ema_ok = False

    atr_ok = (atrp is not None) and (atrp >= atr_min_pct)
    confirm_ok = bool(rsi_ok and ema_ok and atr_ok)

    if not confirm_ok and direction != "side":
        if not rsi_ok: notes.append(f"RSI filter not met (RSI14={rsi14:.1f}).")
        if not ema_ok and ema_required: notes.append("EMA structure not aligned with direction.")
        if not atr_ok: notes.append(f"ATR% below threshold ({(atrp or 0)*100:.2f}% < {atr_min_pct*100:.2f}%).")

    use_pct_targets = bool(prof.get("use_pct_targets", False))
    sl_pct = float(prof.get("sl_pct", 0.03))
    tp_pcts: List[float] = list(prof.get("tp_pcts", [0.03, 0.07, 0.12]))

    entry = sl = None
    take_profits: Dict[str, float] = {}

    if direction == "side" or not confirm_ok:
        notes.append("No trade suggestion.")
    else:
        entry = close
        if use_pct_targets:
            if direction == "up":
                sl = entry * (1 - sl_pct)
                tps = [entry * (1 + p) for p in tp_pcts]
            else:
                sl = entry * (1 + sl_pct)
                tps = [entry * (1 - p) for p in tp_pcts]
            take_profits = {f"TP{i+1}": float(tp) for i, tp in enumerate(tps)}
        else:
            if direction == "up":
                sl = float(recent_low) if recent_low else None
                candidates = [("TP1", ext_1272), ("TP2", ext_1618), ("TP3", ext_20)]
                take_profits = {k: v for k, v in candidates if v and v > entry}
                if not take_profits and recent_high and recent_high > entry:
                    take_profits = {"TP1": recent_high}
            else:
                sl = float(recent_high) if recent_high else None
                candidates = [("TP1", ext_1272), ("TP2", ext_1618), ("TP3", ext_20)]
                take_profits = {k: v for k, v in candidates if v and v < entry}
                if not take_profits and recent_low and recent_low < entry:
                    take_profits = {"TP1": recent_low}

    return {
        "symbol": symbol,
        "tf": tf,
        "direction": direction,
        "percent": perc,
        "entry": entry,
        "stop_loss": sl,
        "take_profits": take_profits,
        "note": " | ".join(notes) if notes else None,
        "scenarios": sc,
    }

# =============================================================================
# FORMATTER
# -----------------------------------------------------------------------------
def format_trade_text(s: Dict[str, object]) -> str:
    sym = s.get("symbol", "")
    tf = s.get("tf", "")
    direction = str(s.get("direction", "")).upper()
    perc = s.get("percent", {}) or {}
    up_p = perc.get("up", 0)
    down_p = perc.get("down", 0)
    side_p = perc.get("side", 0)

    entry = _fmt(s.get("entry"))
    sl = _fmt(s.get("stop_loss"))
    tps = s.get("take_profits", {}) or {}
    tp_list = " / ".join([_fmt(tps[k]) for k in ["TP1", "TP2", "TP3"] if k in tps]) or "-"
    lines = [
        f"📊 {sym} {tf}",
        f"UP {up_p}% | DOWN {down_p}% | SIDE {side_p}%",
        f"🎯 {direction}",
        f"Entry: {entry} | SL: {sl} | TP: {tp_list}",
    ]
    if s.get("note"):
        lines.append(f"ℹ️ {s['note']}")
    return "\n".join(lines)
