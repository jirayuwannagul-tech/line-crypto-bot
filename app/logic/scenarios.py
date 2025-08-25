# app/logic/scenarios.py
# เลเยอร์ LOGIC เท่านั้น — อ้างอิงกฎ/ตัววิเคราะห์จาก app.analysis.* โดยไม่แก้กฎ
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import os
import math
import numpy as np
import pandas as pd

# ✅ ใช้โมดูลใน analysis เท่านั้น (ไม่แก้กฎ)
from app.analysis.indicators import apply_indicators
from app.analysis.fibonacci import fib_levels, fib_extensions, detect_fib_cluster, merge_levels
from app.analysis import elliott as ew  # ใช้ rule จาก analysis

# Dow: safe import
try:
    from app.analysis.dow import analyze_dow as _analyze_dow  # type: ignore
except Exception:
    _analyze_dow = None  # type: ignore

# Logic layer: ใช้ elliott_logic (blend weekly context ได้)
try:
    from app.logic.elliott_logic import classify_elliott_with_kind
except Exception:
    classify_elliott_with_kind = None

__all__ = ["analyze_scenarios"]

# =============================================================================
# Profile defaults / safe loader
# =============================================================================
_DEFAULTS: Dict = {
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
        "side_range_threshold": 0.035,
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

# =============================================================================
# Internal utils
# =============================================================================
def _fractals(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[pd.Series, pd.Series]:
    n = len(df)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    high, low = df["high"].values, df["low"].values
    for i in range(left, n - right):
        win_h = high[i - left : i + right + 1]
        win_l = low[i - left : i + right + 1]
        if np.argmax(win_h) == left and high[i] == win_h.max():
            sh[i] = True
        if np.argmin(win_l) == left and low[i] == win_l.min():
            sl[i] = True
    return pd.Series(sh, index=df.index), pd.Series(sl, index=df.index)

def _recent_swings(df: pd.DataFrame, k: int = 9) -> Dict[str, float]:
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

    last_type, last_price = sw_rows[-1][1], sw_rows[-1][2]
    prev = None
    for j in range(len(sw_rows) - 2, -1, -1):
        if sw_rows[j][1] != last_type:
            prev = sw_rows[j]
            break

    out: Dict[str, float] = {
        "last_swing_type": last_type,
        "last_swing_price": last_price,
        "recent_high": max(p for _, t, p in sw_rows if t == "H")
        if any(t == "H" for _, t, _ in sw_rows)
        else float(df["high"].tail(20).max()),
        "recent_low": min(p for _, t, p in sw_rows if t == "L")
        if any(t == "L" for _, t, _ in sw_rows)
        else float(df["low"].tail(20).min()),
    }
    if prev:
        out.update(
            {
                "prev_swing_type": prev[1],
                "prev_swing_price": prev[2],
                "leg_A": prev[2],
                "leg_B": last_price,
                "leg_dir": "up" if last_price > prev[2] else "down" if last_price < prev[2] else "side",
            }
        )
    return out

def _softmax3(u: float, d: float, s: float) -> Tuple[float, float, float]:
    arr = np.array([u, d, s], dtype=float)
    m = np.max(arr)
    e = np.exp(arr - m)
    p = e / e.sum()
    return float(p[0]), float(p[1]), float(p[2])

def _pct(x: float) -> int:
    return int(round(100 * x))

def _analyze_dow_safe(df_ind: pd.DataFrame) -> Dict[str, object]:
    try:
        if callable(_analyze_dow):
            return _analyze_dow(df_ind)  # type: ignore[misc]
    except Exception:
        pass
    ema50 = float(df_ind["ema50"].iloc[-1]) if "ema50" in df_ind else float("nan")
    ema200 = float(df_ind["ema200"].iloc[-1]) if "ema200" in df_ind else float("nan")
    close = float(df_ind["close"].iloc[-1])
    trend = "SIDE"
    conf = 50
    if not any(math.isnan(x) for x in (ema50, ema200, close)):
        if close > ema200 and ema50 > ema200:
            trend, conf = "UP", 65
        elif close < ema200 and ema50 < ema200:
            trend, conf = "DOWN", 65
        else:
            trend, conf = "SIDE", 55
    return {"trend_primary": trend, "confidence": conf}

# -------------------------
# Elliott Guess Heuristic 🆕
# -------------------------
def _elliott_guess_when_unknown(
    *,
    close: float,
    ema50: float,
    ema200: float,
    recent_low: Optional[float],
    recent_high: Optional[float],
    leg_dir: Optional[str],
) -> str:
    """
    คาดเดาอย่างระมัดระวังเมื่อ pattern ยัง UNKNOWN
    - ถ้าแนวโน้มขาลงเด่น (leg_dir == down) และราคาใกล้/ต่ำกว่า recent_low → เดา Wave 3 ลง
    - ถ้าขึ้นเด่น (leg_dir == up) และราคาอยู่เหนือ EMA50 และถือ recent_low ได้ → เดา Wave C/3 ขึ้น
    - ไม่เข้าเงื่อนไข → เดา Side/Triangle
    """
    guess = "Side/Triangle (ยังไม่ชัด)"
    if not (close and ema50 and ema200):
        return guess

    # safety thresholds
    near_pct = 0.0045  # ~0.45% ใกล้แนวรับ-ต้าน
    def _near(x: Optional[float]) -> bool:
        if x is None or x <= 0:
            return False
        return abs(close - x) / x <= near_pct

    if leg_dir == "down":
        if recent_low and (close < recent_low or _near(recent_low)):
            return "Wave 3 ลง (ถ้าหลุด Low ต่อเนื่อง)"
        # ถ้าต่ำกว่า ema50/ema200 ก็ยัง bias ลง
        if close < ema50 and ema50 <= ema200:
            return "Wave 3 ลง (โครงสร้าง EMA เอียงลง)"
    elif leg_dir == "up":
        if close > ema50 and (recent_low is not None) and (close > recent_low):
            return "Wave C/3 ขึ้น (ถ้ายืนเหนือ EMA50)"
        if recent_high and _near(recent_high):
            return "Wave 5/ต่อเนื่อง ขึ้น (ทดสอบ High)"

    return guess

# =============================================================================
# Public API
# =============================================================================
def analyze_scenarios(
    df: Optional[pd.DataFrame],
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
    weekly_ctx: Optional[Dict] = None,  # 🆕 บริบทจาก 1W
) -> Dict[str, object]:
    if df is None:
        raise ValueError("analyze_scenarios: df is None")

    if len(df) < 30:
        return {
            "percent": {"up": 33, "down": 33, "side": 34},
            "levels": {},
            "rationale": ["Data too short → neutral."],
            "meta": {"symbol": symbol, "tf": tf},
        }

    cfg = cfg or {}
    profile_name = str(cfg.get("profile", "baseline"))
    prof = _get_profile(tf, profile_name)

    # Indicators
    df_ind = apply_indicators(df, cfg.get("ind_cfg"))
    last = df_ind.iloc[-1]

    # Dow & Elliott
    dow = _analyze_dow_safe(df_ind)
    if classify_elliott_with_kind:
        ell = classify_elliott_with_kind(df_ind, timeframe=tf, weekly_det=weekly_ctx)
    else:
        ell = {"pattern": "UNKNOWN", "current": {"direction": "side"}}

    # Swings + Fibo
    sw_meta = _recent_swings(df_ind, k=9)
    fibo_levels: Dict[str, Optional[float]] = {}
    cluster_info: Optional[Dict] = None
    if "leg_A" in sw_meta and "leg_B" in sw_meta and sw_meta.get("leg_dir") in ("up", "down"):
        A, B = sw_meta["leg_A"], sw_meta["leg_B"]
        retr = fib_levels(A, B, ratios=tuple(prof["fibo"]["retr"]))["levels"]
        exts = fib_extensions(A, B, ratios=tuple(prof["fibo"]["ext"]))["levels"]
        fibo_levels = {
            "retr_0.382": retr.get("0.382"),
            "retr_0.5": retr.get("0.5"),
            "retr_0.618": retr.get("0.618"),
            "ext_1.272": exts.get("1.272"),
            "ext_1.618": exts.get("1.618"),
        }
        merged = merge_levels(retr, exts)
        cluster_info = detect_fib_cluster(
            merged,
            tolerance_pct=float(prof["fibo"]["cluster_tolerance"]),
            min_points=2,
        )

    # Voting logic (คล้ายเดิม แต่รวม context 1W ถ้ามี)
    up_logit = down_logit = side_logit = 0.0
    notes: List[str] = []
    vw = prof["voting"]
    iw, dw, ew_w = float(vw["indicators_weight"]), float(vw["dow_weight"]), float(vw["elliott_weight"])

    # Dow
    dp, dc = dow.get("trend_primary", "SIDE"), int(dow.get("confidence", 50))
    if dp == "UP":
        up_logit += 1.6 * dw
        notes.append(f"Dow UP (conf={dc})")
    elif dp == "DOWN":
        down_logit += 1.6 * dw
        notes.append(f"Dow DOWN (conf={dc})")
    else:
        side_logit += 0.7 * dw
        notes.append("Dow SIDE")

    # Elliott
    patt, edir, kind = (
        ell.get("pattern", "UNKNOWN"),
        (ell.get("current") or {}).get("direction", "side"),
        ell.get("kind", "UNKNOWN"),
    )
    if kind == "IMPULSE_PROGRESS":
        up_logit += 1.5 * ew_w
        notes.append("Elliott Impulse UP")
    elif kind == "IMPULSE_TOP":
        down_logit += 1.5 * ew_w
        notes.append("Elliott Impulse TOP")
    elif kind == "CORRECTION":
        down_logit += 1.0 * ew_w
        side_logit += 0.5 * ew_w
        notes.append("Elliott Correction")
    else:
        # ยัง UNKNOWN → ใส่ UNKNOWN ก่อน
        side_logit += 0.4 * ew_w
        notes.append(f"Elliott {patt}")

        # 🆕 Elliott Guess (heuristic) — ไม่แตะไฟล์กฎ
        ema50 = float(last.get("ema50", np.nan))
        ema200 = float(last.get("ema200", np.nan))
        close = float(last.get("close", np.nan))
        guess = _elliott_guess_when_unknown(
            close=close,
            ema50=ema50 if not math.isnan(ema50) else 0.0,
            ema200=ema200 if not math.isnan(ema200) else 0.0,
            recent_low=sw_meta.get("recent_low"),
            recent_high=sw_meta.get("recent_high"),
            leg_dir=sw_meta.get("leg_dir"),
        )
        notes.append(f"Elliott Guess: {guess}")

        # ให้ logit ขยับเล็กน้อยตาม guess (น้ำหนักนุ่มๆ)
        if "ลง" in guess:
            down_logit += 0.25 * ew_w
        elif "ขึ้น" in guess:
            up_logit += 0.25 * ew_w
        else:
            side_logit += 0.15 * ew_w

    # Weekly context blend 🆕
    wk_bias = (ell.get("current") or {}).get("weekly_bias", "neutral")
    if wk_bias == "up":
        up_logit += 0.8
        notes.append("Weekly context: UP bias")
    elif wk_bias == "down":
        down_logit += 0.8
        notes.append("Weekly context: DOWN bias")

    # Indicators
    rsi = float(last.get("rsi14", np.nan))
    macd_hist = float(last.get("macd_hist", np.nan))
    ema50 = float(last.get("ema50", np.nan))
    ema200 = float(last.get("ema200", np.nan))
    close = float(last.get("close", np.nan))

    if not math.isnan(rsi):
        if rsi >= float(prof["confirm"]["rsi_bull_min"]):
            up_logit += 0.8 * iw
        elif rsi <= float(prof["confirm"]["rsi_bear_max"]):
            down_logit += 0.8 * iw
        else:
            side_logit += 0.3 * iw

    if not math.isnan(macd_hist):
        if macd_hist > 0:
            up_logit += prof["momentum_triggers"]["macd_hist_bias_weight"] * iw
        elif macd_hist < 0:
            down_logit += prof["momentum_triggers"]["macd_hist_bias_weight"] * iw

    if not any(math.isnan(x) for x in (ema50, ema200, close)):
        if close > ema200 and ema50 > ema200:
            up_logit += 0.9 * iw
        elif close < ema200 and ema50 < ema200:
            down_logit += 0.9 * iw
        else:
            side_logit += 0.4 * iw

    rng = float(df_ind["high"].tail(20).max() - df_ind["low"].tail(20).min())
    if close > 0 and rng / close < float(vw["side_range_threshold"]):
        side_logit += 0.8

    if cluster_info:
        if profile_name == "chinchot":
            if sw_meta.get("leg_dir") == "up":
                up_logit += 0.6
            elif sw_meta.get("leg_dir") == "down":
                down_logit += 0.6
        else:
            if sw_meta.get("leg_dir") == "up":
                up_logit += 0.3
            elif sw_meta.get("leg_dir") == "down":
                down_logit += 0.3

    # Convert logits → percentage
    pu, pd, ps = _softmax3(up_logit, down_logit, side_logit)

    levels = {
        "recent_high": sw_meta.get("recent_high"),
        "recent_low": sw_meta.get("recent_low"),
        "ema50": None if math.isnan(ema50) else ema50,
        "ema200": None if math.isnan(ema200) else ema200,
        "fibo": fibo_levels,
        "elliott": ell,
        "fib_cluster": cluster_info,
    }

    payload = {
        "percent": {"up": _pct(pu), "down": _pct(pd), "side": _pct(ps)},
        "levels": levels,
        "rationale": notes[:15],
        "meta": {"symbol": symbol, "tf": tf, "profile": profile_name, "dow": dow},
    }
    total = sum(payload["percent"].values())
    if total != 100:
        diff = 100 - total
        payload["percent"]["side"] = max(0, min(100, payload["percent"]["side"] + diff))
    return payload
