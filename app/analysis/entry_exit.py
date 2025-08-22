# app/analysis/entry_exit.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# อธิบาย:
# - สร้างคำแนะนำ Entry/SL/TP โดยยึด Elliott เป็นแกน ผ่านผลจาก scenarios()
# - รองรับ "โปรไฟล์" (baseline / cholak / chinchot) ที่มากำหนดเกณฑ์ยืนยันสัญญาณ
#   และรูปแบบการตั้งเป้าหมายราคา (Fibonacci / เปอร์เซ็นต์)
# - ไม่ทำให้ API เดิมพัง: คง signature ฟังก์ชัน suggest_trade() / format_trade_text()
# =============================================================================

from __future__ import annotations
from typing import Dict, Optional, Tuple, List
import os
import math

import pandas as pd

from .scenarios import analyze_scenarios
from .indicators import apply_indicators

__all__ = ["suggest_trade", "format_trade_text"]

# =============================================================================
# LAYER B) SMALL HELPERS
# -----------------------------------------------------------------------------
def _rr(entry: float, sl: float, tp: float) -> Optional[float]:
    """คำนวณ Risk:Reward (R:R). ถ้าข้อมูลไม่ครบ คืน None"""
    if entry is None or sl is None or tp is None:
        return None
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk == 0:
        return None
    return reward / risk

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

    # overrides.by_timeframe
    ov = (prof.get("overrides", {}) or {}).get("by_timeframe", {}) if isinstance(prof, dict) else {}
    if tf in ov:
        merged = _merge(merged, ov[tf])
    return merged

def _atr_pct(df: pd.DataFrame, n: int = 14) -> Optional[float]:
    """ATR เป็นสัดส่วนของราคาปิดล่าสุด (ATR%)"""
    import numpy as np  # local import เพื่อเลี่ยง dependency ตอนทดสอบ
    if len(df) < n + 1:
        return None
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    last_close = float(c.iloc[-1])
    if last_close == 0 or math.isnan(last_close):
        return None
    return float(atr.iloc[-1] / last_close)

# =============================================================================
# LAYER C) CORE LOGIC (PROFILE-AWARE ENTRY/EXIT)
# -----------------------------------------------------------------------------
def suggest_trade(
    df: Optional[pd.DataFrame],
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    สร้างคำแนะนำจุดเข้า/TP/SL แบบ Elliott-centric พร้อมคอนเฟิร์มด้วย EMA/RSI/ATR
    - ยึด payload จาก analyze_scenarios() แล้วปรับตามโปรไฟล์
    """
    cfg = cfg or {}

    # --- Patch 1: auto-load df if not provided ---
    if df is None:
        try:
            # ใช้ relative import ให้สอดคล้องกับโครงสร้างแพ็กเกจ
            from .timeframes import get_data
        except Exception:
            # fallback absolute import กรณีสคริปต์ถูกรันแบบแยก
            from app.analysis.timeframes import get_data  # type: ignore
        xlsx_path = cfg.get("xlsx_path") if isinstance(cfg, dict) else None
        try:
            df = get_data(symbol, tf, xlsx_path=xlsx_path)
        except Exception as e:
            raise RuntimeError(f"cannot load dataframe for {symbol} {tf}: {e}")

    # 0) โหลดโปรไฟล์ (ปลอดภัยแม้ไม่มี YAML)
    profile_name = str(cfg.get("profile", "baseline"))
    prof = _get_profile(tf, profile_name)

    # 1) สรุปภาพรวมด้วย scenarios (ภายในจะคิด Elliott/Dow/Indicators + Fibo cluster แล้ว)
    sc = analyze_scenarios(df, symbol=symbol, tf=tf, cfg={"profile": profile_name, **cfg})

    # 2) เตรียมอินดิเคเตอร์ล่าสุดเพื่อใช้คอนเฟิร์ม (RSI/EMA/ATR%)
    df_ind = apply_indicators(df, cfg.get("ind_cfg", None))
    last = df_ind.iloc[-1]
    close = float(last["close"])
    ema50 = float(last.get("ema50"))
    ema200 = float(last.get("ema200"))
    rsi14 = float(last.get("rsi14"))
    atrp = _atr_pct(df_ind, n=int(cfg.get("atr_period", 14)))

    # 3) เลือกทิศทางจากเปอร์เซ็นต์มากสุด + ตรวจ Threshold ขั้นต่ำ (min_prob)
    perc: Dict[str, int] = sc.get("percent", {"up": 33, "down": 33, "side": 34})
    direction = max(perc, key=perc.get)  # "up"|"down"|"side"
    min_prob = float(prof.get("min_prob", 0))
    notes: List[str] = []

    if perc.get(direction, 0) < min_prob:
        notes.append(f"Confidence below threshold: {perc.get(direction, 0)}% < {min_prob}%")

    # 4) ดึงระดับสำคัญจาก scenarios (recent highs/lows, fib extensions, cluster)
    levels = sc.get("levels", {}) or {}
    recent_high = levels.get("recent_high")
    recent_low = levels.get("recent_low")
    fibo = levels.get("fibo", {}) or {}
    ext_1272 = fibo.get("ext_1.272")
    ext_1618 = fibo.get("ext_1.618")
    ext_20   = fibo.get("ext_2.0")
    fib_cluster = levels.get("fib_cluster")  # {"center":..., "members":[(key,price)], "spread_pct":...}

    # 5) เงื่อนไขคอนเฟิร์มตามโปรไฟล์
    rsi_ok = True
    ema_ok = True
    atr_ok = True

    rsi_bull_min = float(prof["confirm"]["rsi_bull_min"])
    rsi_bear_max = float(prof["confirm"]["rsi_bear_max"])
    ema_required = bool(prof["confirm"]["ema_structure_required"])
    atr_min_pct = float(prof["confirm"]["atr_min_pct"])

    if direction == "up":
        rsi_ok = (not math.isnan(rsi14)) and (rsi14 >= rsi_bull_min)
        ema_ok = (close > ema200 and ema50 > ema200) if ema_required else True
    elif direction == "down":
        rsi_ok = (not math.isnan(rsi14)) and (rsi14 <= rsi_bear_max)
        ema_ok = (close < ema200 and ema50 < ema200) if ema_required else True
    else:
        rsi_ok = ema_ok = False

    atr_ok = (atrp is not None) and (atrp >= atr_min_pct)

    # Special handling: โปรไฟล์ "chinchot" อนุญาต early entry ถ้าอยู่ใกล้ Fibo cluster
    early_entry = False
    if profile_name == "chinchot" and direction in ("up", "down") and fib_cluster and "center" in fib_cluster:
        center = float(fib_cluster["center"])
        dist_pct = abs(close - center) / center if center else 1.0
        tol = float(prof["fibo"]["cluster_tolerance"]) * 1.2
        if dist_pct <= tol:
            early_entry = True
            if direction == "up" and not rsi_ok and rsi14 >= (rsi_bull_min - 2):
                rsi_ok = True; notes.append("Early entry near Fibo cluster (RSI relaxed).")
            if direction == "down" and not rsi_ok and rsi14 <= (rsi_bear_max + 2):
                rsi_ok = True; notes.append("Early entry near Fibo cluster (RSI relaxed).")

    confirm_ok = bool(rsi_ok and ema_ok and atr_ok)
    if not confirm_ok and direction != "side":
        if not rsi_ok: notes.append(f"RSI filter not met (RSI14={rsi14:.1f}).")
        if not ema_ok and ema_required: notes.append("EMA structure not aligned with direction.")
        if not atr_ok: notes.append(f"ATR% below threshold ({(atrp or 0)*100:.2f}% < {atr_min_pct*100:.2f}%).")

    # 6) กำหนด Entry/SL/TP ตามโหมดของโปรไฟล์
    use_pct_targets = bool(prof.get("use_pct_targets", False))
    sl_pct = float(prof.get("sl_pct", 0.03))
    tp_pcts: List[float] = list(prof.get("tp_pcts", [0.03, 0.07, 0.12]))

    entry: Optional[float] = None
    sl: Optional[float] = None
    take_profits: Dict[str, float] = {}

    if direction == "side":
        entry = None
        sl = None
        notes.append("Market is SIDE (no entry suggested).")
    elif not confirm_ok:
        entry = None
        sl = None
        notes.append("Signal not confirmed; waiting.")
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
            # โหมด Fibonacci/Swing
            if direction == "up":
                sl = float(recent_low) if recent_low is not None else None
                candidates: List[Tuple[str, Optional[float]]] = [
                    ("TP1", ext_1272),
                    ("TP2", ext_1618),
                    ("TP3", ext_20),
                ]
                take_profits = {k: float(v) for k, v in candidates if v is not None and v > entry}
                if not take_profits and recent_high is not None and recent_high > entry:
                    take_profits = {"TP1": float(recent_high)}
            else:
                sl = float(recent_high) if recent_high is not None else None
                candidates = [
                    ("TP1", ext_1272),
                    ("TP2", ext_1618),
                    ("TP3", ext_20),
                ]
                take_profits = {k: float(v) for k, v in candidates if v is not None and v < entry}
                if not take_profits and recent_low is not None and recent_low < entry:
                    take_profits = {"TP1": float(recent_low)}

    # 7) กรองตาม R:R ขั้นต่ำ (min_rr ของโปรไฟล์)
    min_rr = float(prof.get("min_rr", 0.0))
    if entry is not None and sl is not None and min_rr > 0 and take_profits:
        filtered: Dict[str, float] = {}
        for name, tp in take_profits.items():
            ratio = _rr(entry, sl, tp)
            if ratio is not None and ratio >= min_rr:
                filtered[name] = tp
        if filtered:
            take_profits = filtered
        else:
            notes.append(f"No TP meets R:R ≥ {min_rr}")

    # 8) ผลลัพธ์
    return {
        "symbol": symbol,
        "tf": tf,
        "direction": direction,                 # "up" | "down" | "side"
        "percent": perc,                        # {"up": int, "down": int, "side": int}
        "prob_up": int(perc.get("up", 0)),
        "prob_down": int(perc.get("down", 0)),
        "entry": entry,                         # float | None
        "stop_loss": sl,                        # float | None
        "take_profits": take_profits,           # {"TP1": float, "TP2": float, "TP3": float}
        "note": " | ".join(notes) if notes else None,
        "scenarios": sc,                        # แนบผลวิเคราะห์เต็มไว้ใช้งานต่อ
        "config_used": {
            "profile": profile_name,
            "use_pct_targets": use_pct_targets,
            "sl_pct": sl_pct,
            "tp_pcts": tp_pcts,
            "min_prob": min_prob,
            "min_rr": min_rr,
            "confirm": prof.get("confirm", {}),
        },
    }

# =============================================================================
# LAYER D) TEXT FORMATTER (unchanged interface)
# -----------------------------------------------------------------------------
def format_trade_text(s: Dict[str, object]) -> str:
    """
    แปลงผลลัพธ์จาก suggest_trade() เป็นข้อความสั้นๆ สำหรับตอบใน LINE
    รวม % ขาขึ้น/ขาลง ให้ชัดเจน
    """
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
    # ให้เรียง TP ตามชื่อ TP1, TP2, TP3
    tp_items = []
    for key in ["TP1", "TP2", "TP3"]:
        if key in tps:
            tp_items.append(_fmt(tps[key]))
    if not tp_items:
        tp_items = [_fmt(v) for _, v in sorted(tps.items())]
    tp_list = " / ".join(tp_items) if tp_items else "-"

    lines = [
        f"📊 {sym} {tf} — สรุปสัญญาณ",
        f"UP {up_p}% | DOWN {down_p}% | SIDE {side_p}%",
        "",
        f"🎯 ทางเลือก (bias): {direction}",
        f"• Entry: {entry}",
        f"• SL: {sl}",
        f"• TP: {tp_list}",
    ]
    note = s.get("note")
    if note:
        lines += ["", f"ℹ️ {note}"]
    return "\n".join(lines)
