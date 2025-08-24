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
from app.analysis import elliott as ew  # ต้องใช้ฟังก์ชันจากโมดูลนี้

# Dow: safe import (ถ้าไม่มี analyze_dow จะ fallback)
try:
    from app.analysis.dow import analyze_dow as _analyze_dow  # type: ignore
except Exception:
    _analyze_dow = None  # type: ignore

__all__ = ["analyze_scenarios"]

# =============================================================================
# Profile defaults / safe loader (ปรับได้ใน logic)
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
# Internal utils (logic-layer)
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
    # เพิ่มความไวเก็บ swing มากขึ้น (k=9) เพื่อช่วยจับปลายคลื่น/บริเวณ TOP/BOTTOM
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
    """
    adapter สำหรับเรียก Dow analysis แบบไม่พึ่งพาฟังก์ชันเฉพาะชื่อ
    - ถ้ามี _analyze_dow: เรียกใช้ตรงๆ
    - ถ้าไม่มี: ทำ fallback แบบเบาๆ จาก EMA เพื่อคืนค่าโครงสร้างเดียวกัน
    """
    try:
        if callable(_analyze_dow):
            return _analyze_dow(df_ind)  # type: ignore[misc]
    except Exception:
        pass
    # Fallback: ประเมินเทรนด์จาก EMA50/EMA200 แบบหยาบ
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


def _analyze_elliott_safe(
    df_ind: pd.DataFrame,
    *,
    pivot_left: int = 2,
    pivot_right: int = 2,
) -> Dict[str, object]:
    """
    adapter สำหรับ Elliott:
    - ถ้าโมดูลมี `analyze_elliott` → ใช้อันนั้น
    - ถ้าไม่มีแต่มี `analyze_elliott_rules` → ใช้อันนั้นแทน (ส่ง kwargs ที่รองรับ)
    - ถ้าไม่มีทั้งคู่ → fallback เป็น UNKNOWN (แต่ให้ direction ประเมินหยาบ)
    """
    # 1) analyze_elliott (ถ้ามี)
    if hasattr(ew, "analyze_elliott") and callable(getattr(ew, "analyze_elliott")):
        try:
            return ew.analyze_elliott(df_ind, pivot_left=pivot_left, pivot_right=pivot_right)  # type: ignore[attr-defined]
        except Exception:
            pass

    # 2) analyze_elliott_rules (ถ้ามี)
    if hasattr(ew, "analyze_elliott_rules") and callable(getattr(ew, "analyze_elliott_rules")):
        try:
            # บาง implementation อาจไม่รองรับ pivot_* → ส่งเฉพาะ df_ind
            return ew.analyze_elliott_rules(df_ind)  # type: ignore[attr-defined]
        except Exception:
            pass

    # 3) Fallback: UNKNOWN + ประเมิน direction หยาบ ๆ จาก EMA
    ema50 = float(df_ind["ema50"].iloc[-1]) if "ema50" in df_ind else float("nan")
    ema200 = float(df_ind["ema200"].iloc[-1]) if "ema200" in df_ind else float("nan")
    close = float(df_ind["close"].iloc[-1])
    direction = "side"
    if not any(math.isnan(x) for x in (ema50, ema200, close)):
        if close > ema200 and ema50 > ema200:
            direction = "up"
        elif close < ema200 and ema50 < ema200:
            direction = "down"
    return {"pattern": "UNKNOWN", "completed": False, "current": {"direction": direction}, "targets": {}}


# =============================================================================
# Public API (logic-layer)
# =============================================================================
def analyze_scenarios(
    df: Optional[pd.DataFrame],
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    if df is None:
        raise ValueError("analyze_scenarios: df is None")

    if len(df) < 50:
        return {
            "percent": {"up": 33, "down": 33, "side": 34},
            "levels": {},
            "rationale": ["Data too short → neutral."],
            "meta": {"symbol": symbol, "tf": tf},
        }

    cfg = cfg or {}
    profile_name = str(cfg.get("profile", "baseline"))
    prof = _get_profile(tf, profile_name)

    # Indicators (คำนวณจาก analysis.indicators)
    df_ind = apply_indicators(df, cfg.get("ind_cfg"))
    last = df_ind.iloc[-1]

    # Dow & Elliott (วิเคราะห์ด้วยโมดูลกฎ)
    dow = _analyze_dow_safe(df_ind)
    ell = _analyze_elliott_safe(
        df_ind,
        pivot_left=cfg.get("pivot_left", 2),
        pivot_right=cfg.get("pivot_right", 2),
    )

    # Swings + Fibo (logic เลือกใช้จาก analysis.fibonacci)
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

    # Voting logic
    up_logit = down_logit = side_logit = 0.0
    notes: List[str] = []
    vw = prof["voting"]
    iw, dw, ew_w = float(vw["indicators_weight"]), float(vw["dow_weight"]), float(vw["elliott_weight"])

    # Dow contribution
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

    # Elliott contribution
    patt, edir = ell.get("pattern", "UNKNOWN"), (ell.get("current") or {}).get("direction", "side")
    if patt in ("IMPULSE", "DIAGONAL"):
        if edir == "up":
            up_logit += 1.5 * ew_w
            notes.append(f"Elliott {patt} UP")
        elif edir == "down":
            down_logit += 1.5 * ew_w
            notes.append(f"Elliott {patt} DOWN")
    else:
        side_logit += 0.4 * ew_w
        notes.append(f"Elliott {patt}")

    # Indicators contribution
    rsi = float(last.get("rsi14", np.nan))
    macd_hist = float(last.get("macd_hist", np.nan))
    ema50, ema200, close = (
        float(last.get("ema50", np.nan)),
        float(last.get("ema200", np.nan)),
        float(last.get("close", np.nan)),
    )

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

    # ตลาดแคบ → เอียงไปทาง SIDE
    rng = float(df_ind["high"].tail(20).max() - df_ind["low"].tail(20).min())
    if close > 0 and rng / close < float(vw["side_range_threshold"]):
        side_logit += 0.8

    # สะสมแต้มจากคลัสเตอร์ฟิโบ
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

    # -------------------------------------------------------------------------
    # Fallback heuristics เมื่อ Elliott = UNKNOWN (ลด bias ไปทาง SIDE/UNKNOWN)
    # -------------------------------------------------------------------------
    if patt == "UNKNOWN":
        try:
            # 1) TOP context → เพิ่ม down_logit (ราคาใกล้ high, RSI สูง แต่ MACD อ่อนแรงลง)
            near_high = False
            if sw_meta.get("recent_high") is not None and close > 0:
                near_high = (abs(close - sw_meta["recent_high"]) / max(close, 1e-9)) <= 0.015

            rsi_ok = (not math.isnan(rsi)) and (rsi >= float(prof["momentum_triggers"].get("rsi_bull_trigger", 57)))

            macd_dim = False
            mh = df_ind["macd_hist"].tail(6)
            if len(mh) >= 6 and mh.notna().all():
                recent3 = float(mh.iloc[-3:].mean())
                prev3 = float(mh.iloc[-6:-3].mean())
                macd_dim = recent3 < prev3

            if sw_meta.get("leg_dir") == "up" and near_high and rsi_ok and macd_dim:
                down_logit += 0.6 * ew_w
                notes.append("Fallback: possible TOP (RSI high + MACD dim + near high)")

            # 2) Correction/Down context → เพิ่ม down_logit
            if not any(math.isnan(x) for x in (ema50, ema200, close)):
                if close < ema50 and (not math.isnan(rsi) and rsi <= float(prof["confirm"]["rsi_bear_max"])):
                    down_logit += 0.45 * iw
                    notes.append("Fallback: correction bias (close<EMA50 & RSI weak)")

            # 3) Progress up context → เพิ่ม up_logit
            if not any(math.isnan(x) for x in (ema50, ema200, close)):
                bull = (close > ema200 and ema50 > ema200) and (not math.isnan(rsi) and rsi >= float(prof["confirm"]["rsi_bull_min"]))
                if bull and sw_meta.get("leg_dir") == "up":
                    up_logit += 0.45 * iw
                    notes.append("Fallback: progress bias (EMA bull + RSI strong + leg up)")
        except Exception:
            pass

    # Convert logits → percentage
    pu, pd, ps = _softmax3(up_logit, down_logit, side_logit)

    levels = {
        "recent_high": sw_meta.get("recent_high"),
        "recent_low": sw_meta.get("recent_low"),
        "ema50": None if math.isnan(ema50) else ema50,
        "ema200": None if math.isnan(ema200) else ema200,
        "fibo": fibo_levels,
        "elliott_targets": ell.get("targets", {}),
        "fib_cluster": cluster_info,
    }

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
            "swings": {
                k: v
                for k, v in sw_meta.items()
                if k in ("last_swing_type", "last_swing_price", "prev_swing_type", "prev_swing_price", "leg_dir")
            },
        },
    }
    # ensure sum 100
    total = sum(payload["percent"].values())
    if total != 100:
        diff = 100 - total
        payload["percent"]["side"] = max(0, min(100, payload["percent"]["side"] + diff))
    return payload
