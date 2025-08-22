# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# อธิบาย:
# - รวม Dow + Elliott + Fibonacci + Indicators แล้วสรุป %UP/%DOWN/%SIDE
# - เพิ่ม "โปรไฟล์" (baseline / cholak / chinchot) เพื่อปรับน้ำหนักตัดสินใจ
# - รองรับ Fibo Cluster เป็นโซนยืนยัน/จังหวะเข้า โดยไม่ทำให้ API เดิมพัง
#
# Public API:
#   analyze_scenarios(df: pd.DataFrame, symbol="BTCUSDT", tf="1D", cfg=None) -> Dict
#
# cfg ตัวอย่าง:
#   {
#     "profile": "chinchot",              # หรือ "cholak" / "baseline"
#     "ind_cfg": {...},                   # ส่งต่อไป apply_indicators
#     "pivot_left": 2, "pivot_right": 2,  # ส่งต่อให้ analyze_elliott
#   }
# =============================================================================
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import os
import math
import numpy as np
import pandas as pd

from .indicators import apply_indicators
from .dow import analyze_dow
from .fibonacci import fib_levels, fib_extensions, detect_fib_cluster, merge_levels
from . import elliott as ew  # analyze_elliott

# =============================================================================
# LAYER B) PROFILE LOADING (SAFE)
# -----------------------------------------------------------------------------
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
        "ext": [1.272, 1.618],
        "cluster_tolerance": 0.0035,
    },
    "voting": {
        "elliott_weight": 1.10,
        "dow_weight": 0.90,
        "indicators_weight": 0.70,
        "side_range_threshold": 0.035,  # 20-bar range / price < threshold → SIDE bias
    },
    "momentum_triggers": {
        "rsi_bull_trigger": 57,
        "rsi_bear_trigger": 43,
        "macd_hist_bias_weight": 0.15,
    },
}

def _safe_load_yaml(path: str) -> Optional[Dict]:
    try:
        import yaml
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        return None
    return None

def _merge(a: Dict, b: Dict) -> Dict:
    """merge แบบลึก — b ทับ a"""
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

    # overrides.by_timeframe
    ov = (prof.get("overrides", {}) or {}).get("by_timeframe", {}) if isinstance(prof, dict) else {}
    if tf in ov:
        merged = _merge(merged, ov[tf])
    return merged

# =============================================================================
# LAYER C) INTERNAL UTILITIES (pivots/swings/softmax)
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

def _recent_swings(df: pd.DataFrame, k: int = 7) -> Dict[str, float]:
    """ดึงข้อมูลสวิงล่าสุดและ A->B leg สำหรับวัด Fibo"""
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
    sw_rows = sw_rows[-max(2, k):]

    last_type = sw_rows[-1][1]
    last_price = sw_rows[-1][2]
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
    arr = np.array([u, d, s], dtype=float)
    m = np.max(arr)
    e = np.exp(arr - m)
    p = e / e.sum()
    return float(p[0]), float(p[1]), float(p[2])

def _pct(x: float) -> int:
    return int(round(100 * x))

# =============================================================================
# LAYER D) CORE: ANALYZE SCENARIOS (PROFILE-AWARE)
# -----------------------------------------------------------------------------
def analyze_scenarios(
    df: Optional[pd.DataFrame],
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

    # --- Guard --- df ต้องไม่ None
    if df is None:
        raise ValueError(
            "analyze_scenarios: df is None (no data). "
            "Pass a DataFrame or let the caller load it first."
        )

    if len(df) < 50:
        return {
            "percent": {"up": 33, "down": 33, "side": 34},
            "levels": {},
            "rationale": ["Data too short, returning neutral probabilities."],
            "meta": {"symbol": symbol, "tf": tf},
        }

    # 0) Profile
    profile_name = str(cfg.get("profile", "baseline"))
    prof = _get_profile(tf, profile_name)

    # 1) Indicators
    df_ind = apply_indicators(df, cfg.get("ind_cfg", None))
    last = df_ind.iloc[-1]

    # 2) Dow & Elliott
    dow = analyze_dow(df_ind)
    ell = ew.analyze_elliott(
        df_ind, pivot_left=cfg.get("pivot_left", 2), pivot_right=cfg.get("pivot_right", 2)
    )

    # 3) Swings & Fibo + Cluster
    sw_meta = _recent_swings(df_ind, k=7)
    fibo_levels: Dict[str, Optional[float]] = {}
    cluster_info: Optional[Dict] = None
    if "leg_A" in sw_meta and "leg_B" in sw_meta and sw_meta.get("leg_dir") in ("up", "down"):
        A = sw_meta["leg_A"]
        B = sw_meta["leg_B"]
        retr = fib_levels(A, B, ratios=tuple(prof["fibo"]["retr"]))["levels"]
        exts = fib_extensions(A, B, ratios=tuple(prof["fibo"]["ext"]))["levels"]
        fibo_levels = {
            "retr_0.382": retr.get("0.382"),
            "retr_0.5": retr.get("0.5"),
            "retr_0.618": retr.get("0.618"),
            "retr_0.786": retr.get("0.786"),  # อาจไม่มีในบางโปรไฟล์
            "ext_1.272": exts.get("1.272"),
            "ext_1.618": exts.get("1.618"),
            "ext_2.0": exts.get("2"),
        }
        merged = merge_levels(retr, exts)
        cluster_info = detect_fib_cluster(
            merged,
            tolerance_pct=float(prof["fibo"]["cluster_tolerance"]),
            min_points=2
        )

    # 4) Voting logic → logits (profile-weighted)
    up_logit = 0.0
    down_logit = 0.0
    side_logit = 0.0
    notes: List[str] = []

    vw = prof["voting"]
    iw = float(vw.get("indicators_weight", 0.7))
    dw = float(vw.get("dow_weight", 0.9))
    ew_w = float(vw.get("elliott_weight", 1.1))

    # Dow primary
    dp = dow.get("trend_primary", "SIDE")
    dc = int(dow.get("confidence", 50))
    if dp == "UP":
        w = (1.0 + (dc - 50) / 100.0) * dw
        up_logit += 1.6 * w
        notes.append(f"Dow primary UP (conf={dc}).")
    elif dp == "DOWN":
        w = (1.0 + (dc - 50) / 100.0) * dw
        down_logit += 1.6 * w
        notes.append(f"Dow primary DOWN (conf={dc}).")
    else:
        side_logit += 0.7 * dw
        notes.append("Dow primary SIDE.")

    # Elliott pattern bias
    patt = ell.get("pattern", "UNKNOWN")
    edir = (ell.get("current", {}) or {}).get("direction", "side")
    if patt in ("IMPULSE", "DIAGONAL"):
        if edir == "up":
            up_logit += 1.5 * ew_w; notes.append(f"Elliott {patt} bias UP.")
        elif edir == "down":
            down_logit += 1.5 * ew_w; notes.append(f"Elliott {patt} bias DOWN.")
    elif patt in ("ZIGZAG", "FLAT", "TRIANGLE"):
        nxt = (ell.get("next", {}) or {}).get("stage", "")
        if "resume_trend_up" in nxt or "thrust_up" in nxt:
            up_logit += 1.1 * ew_w; notes.append(f"Elliott {patt} suggests UP next.")
        elif "resume_trend_down" in nxt or "thrust_down" in nxt:
            down_logit += 1.1 * ew_w; notes.append(f"Elliott {patt} suggests DOWN next.")
        else:
            side_logit += 0.5 * ew_w; notes.append(f"Elliott {patt} unclear.")
    else:
        side_logit += 0.4 * ew_w; notes.append("Elliott UNKNOWN.")

    # Indicators bias (RSI / MACD / EMA)
    rsi = float(last.get("rsi14", np.nan))
    macd_hist = float(last.get("macd_hist", np.nan))
    ema50 = float(last.get("ema50", np.nan))
    ema200 = float(last.get("ema200", np.nan))
    close = float(last.get("close", np.nan))

    # RSI bands (ยึดเกณฑ์โปรไฟล์)
    if not math.isnan(rsi):
        if rsi >= float(prof["confirm"]["rsi_bull_min"]):
            up_logit += 0.8 * iw; notes.append(f"RSI14 {rsi:.1f} bullish.")
        elif rsi <= float(prof["confirm"]["rsi_bear_max"]):
            down_logit += 0.8 * iw; notes.append(f"RSI14 {rsi:.1f} bearish.")
        else:
            side_logit += 0.3 * iw; notes.append(f"RSI14 {rsi:.1f} neutral.")

    # MACD histogram
    if not math.isnan(macd_hist):
        if macd_hist > 0:
            up_logit += float(prof["momentum_triggers"]["macd_hist_bias_weight"]) * iw
            notes.append("MACD histogram > 0.")
        elif macd_hist < 0:
            down_logit += float(prof["momentum_triggers"]["macd_hist_bias_weight"]) * iw
            notes.append("MACD histogram < 0.")

    # EMA structure
    if not any(math.isnan(x) for x in (ema50, ema200, close)):
        if close > ema200 and ema50 > ema200:
            up_logit += 0.9 * iw; notes.append("Price & EMA50 above EMA200.")
        elif close < ema200 and ema50 < ema200:
            down_logit += 0.9 * iw; notes.append("Price & EMA50 below EMA200.")
        else:
            side_logit += 0.4 * iw; notes.append("Mixed EMA structure.")

    # Sideways compression check (ใช้ threshold ตามโปรไฟล์)
    rng = float(df_ind["high"].tail(20).max() - df_ind["low"].tail(20).min())
    lvl = close if not math.isnan(close) else 0.0
    side_th = float(vw.get("side_range_threshold", 0.035))
    if lvl > 0 and rng / lvl < side_th:
        side_logit += 0.8; notes.append(f"20-bar range < {side_th*100:.1f}% → SIDE bias.")

    # Fibo cluster boost (ตามคาแรกเตอร์โปรไฟล์)
    if cluster_info is not None and "center" in cluster_info:
        if profile_name == "chinchot":
            # เชิงรุก: ให้ bias ตามทิศของ leg ปัจจุบัน
            if sw_meta.get("leg_dir") == "up":
                up_logit += 0.6; notes.append("Fibo cluster supports UP timing.")
            elif sw_meta.get("leg_dir") == "down":
                down_logit += 0.6; notes.append("Fibo cluster supports DOWN timing.")
        else:
            # baseline/cholak: cluster เป็น confirm zone (เพิ่มเล็กน้อย)
            if sw_meta.get("leg_dir") == "up":
                up_logit += 0.3; notes.append("Fibo cluster confirms UP zone.")
            elif sw_meta.get("leg_dir") == "down":
                down_logit += 0.3; notes.append("Fibo cluster confirms DOWN zone.")

    # 5) Convert to probabilities
    pu, pd, ps = _softmax3(up_logit, down_logit, side_logit)

    # 6) Key levels (คงรูปแบบเดิม + เพิ่ม cluster)
    levels = {
        "recent_high": sw_meta.get("recent_high"),
        "recent_low": sw_meta.get("recent_low"),
        "ema50": ema50 if not math.isnan(ema50) else None,
        "ema200": ema200 if not math.isnan(ema200) else None,
        "fibo": fibo_levels,
        "elliott_targets": ell.get("targets", {}),
        "fib_cluster": cluster_info,  # {"center":..., "members":[(key,price)...], "spread_pct":...}
    }

    # 7) Compose payload
    payload = {
        "percent": {"up": _pct(pu), "down": _pct(pd), "side": _pct(ps)},
        "levels": levels,
        "rationale": notes[:12],
        "meta": {
            "symbol": symbol,
            "tf": tf,
            "profile": profile_name,
            "dow": dow,
            "elliott": {k: v for k, v in ell.items() if k != "debug"},
            "swings": {k: v for k, v in sw_meta.items() if k in ("last_swing_type","last_swing_price","prev_swing_type","prev_swing_price","leg_dir")},
        },
    }
    # enforce sum = 100 (ปรับ SIDE ให้รวมได้พอดี)
    total = payload["percent"]["up"] + payload["percent"]["down"] + payload["percent"]["side"]
    if total != 100:
        diff = 100 - total
        payload["percent"]["side"] = max(0, min(100, payload["percent"]["side"] + diff))
    return payload
