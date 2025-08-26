# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# - วิเคราะห์และสรุปสัญญาณ Entry/SL/TP (ยึด Scenario + Indicators)
# - รองรับเป้าแบบเปอร์เซ็นต์ (TP 3/5/7%, SL 3%) เป็นค่าเริ่มต้น
# - ดึง context เพิ่มเติม: Recent High/Low, EMA50/EMA200, Elliott Wave, Weekly bias
# - มีทั้ง formatter แบบสั้น และแบบละเอียด (ตามฟอร์แมตที่คุณต้องการ)
# =============================================================================

from __future__ import annotations
from typing import Dict, Optional, Tuple, List
import os
import math
import pandas as pd

# ---- External analysis modules (ของโปรเจกต์เดิม) ---------------------------
from app.logic.scenarios import analyze_scenarios
from app.analysis.indicators import apply_indicators

__all__ = [
    "suggest_trade",                 # core: คำนวณสัญญาณ + บรรจุ context
    "format_trade_text",             # short formatter
    "format_trade_text_detailed",    # detailed formatter (ตามฟอร์แมตตัวอย่าง)
    "suggest_watch_levels",          # helper
]

# =============================================================================
# LAYER B) CONFIG / HELPERS
# -----------------------------------------------------------------------------
_DEFAULTS = {
    "sl_pct": 0.03,                  # SL 3%
    "tp_pcts": [0.03, 0.05, 0.07],   # TP 3/5/7%
}

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

def _extract_wave_label(sc: Dict) -> str:
    """
    พยายามดึงชื่อคลื่นจากหลายคีย์ให้ทนทานที่สุด
    """
    if not isinstance(sc, dict):
        return "Unknown"
    elliott = sc.get("elliott", {}) or {}
    return (
        sc.get("wave_label")
        or sc.get("wave")
        or elliott.get("label")
        or elliott.get("name")
        or elliott.get("stage")
        or sc.get("pattern")
        or "Unknown"
    )

def _extract_dow_label(sc: Dict) -> str:
    if not isinstance(sc, dict):
        return "SIDE"
    return sc.get("dow_label") or sc.get("dow") or "SIDE"

def _atr_pct(df: pd.DataFrame, n: int = 14) -> Optional[float]:
    """
    ATR เป็นสัดส่วนของราคา (เช่น 0.006 = 0.6%)
    """
    if len(df) < n + 1:
        return None
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    last_close = float(c.iloc[-1])
    return None if last_close == 0 or math.isnan(last_close) else float(atr.iloc[-1] / last_close)

# =============================================================================
# LAYER C) WATCH LEVELS
# -----------------------------------------------------------------------------
def suggest_watch_levels(
    *,
    high: Optional[float],
    low: Optional[float],
    price: float,
    atr_pct: Optional[float] = None,
    pct_buffer: float = 0.0025,  # 0.25%
    atr_mult: float = 0.25,      # 0.25 x ATR%
) -> Optional[Tuple[float, float, float]]:
    """
    buffer_abs = max(pct_buffer*price, atr_mult*atr_pct*price)
    long_watch  = high + buffer_abs
    short_watch = low  - buffer_abs
    """
    if high is None or low is None:
        return None
    buf_pct_abs = pct_buffer * price
    buf_atr_abs = (atr_mult * atr_pct * price) if (atr_pct is not None and atr_pct > 0) else 0.0
    buffer_abs = max(buf_pct_abs, buf_atr_abs) if buf_atr_abs > 0 else buf_pct_abs
    return (float(high) + buffer_abs, float(low) - buffer_abs, buffer_abs)

# =============================================================================
# LAYER D) CORE: SUGGEST TRADE
# -----------------------------------------------------------------------------
def suggest_trade(
    df: Optional[pd.DataFrame],
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    คืน dict พร้อม context ครบสำหรับ formatter:
      - direction, probabilities, entry/SL/TP1-3
      - recent_high/low, EMA50/EMA200
      - elliott wave label, weekly bias
    """
    cfg = cfg or {}
    from app.analysis.timeframes import get_data

    # -- Load timeframe data ---------------------------------------------------
    if df is None:
        df = get_data(symbol, tf, xlsx_path=cfg.get("xlsx_path"))

    # -- Analyze current TF ----------------------------------------------------
    sc_1d = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=cfg)
    df_ind = apply_indicators(df, cfg.get("ind_cfg"))
    last = df_ind.iloc[-1]

    close = float(last["close"])
    ema50 = float(last.get("ema50")) if "ema50" in last else None
    ema200 = float(last.get("ema200")) if "ema200" in last else None

    perc: Dict[str, int] = sc_1d.get("percent", {"up": 33, "down": 33, "side": 34})
    direction = max(perc, key=perc.get)

    # -- Weekly context --------------------------------------------------------
    try:
        df_1w = get_data(symbol, "1W", xlsx_path=cfg.get("xlsx_path"))
        sc_1w = analyze_scenarios(df_1w, symbol=symbol, tf="1W", cfg=cfg)
        weekly_bias = (sc_1w.get("bias") or sc_1w.get("trend") or direction).upper()
    except Exception:
        sc_1w = {}
        weekly_bias = direction.upper()

    # -- Recent High/Low จาก scenarios (1D) -----------------------------------
    levels = sc_1d.get("levels", {}) or {}
    recent_high = levels.get("recent_high")
    recent_low = levels.get("recent_low")

    # -- Targets: ใช้ % เสมอตามสเปก ------------------------------------------
    sl_pct = float(cfg.get("sl_pct", _DEFAULTS["sl_pct"]))
    tp_pcts: List[float] = list(cfg.get("tp_pcts", _DEFAULTS["tp_pcts"]))

    entry = close
    if direction == "up":
        sl = entry * (1 - sl_pct)
        tps = [entry * (1 + p) for p in tp_pcts]
    elif direction == "down":
        sl = entry * (1 + sl_pct)
        tps = [entry * (1 - p) for p in tp_pcts]
    else:
        sl = None
        tps = []

    take_profits = {f"TP{i+1}": float(tp) for i, tp in enumerate(tps)}

    # -- ATR% (เพื่อใช้กับ watch levels หากต้องการ) --------------------------
    atrp = _atr_pct(df_ind, n=int(cfg.get("atr_period", 14)))

    # -- Elliott / Dow labels ---------------------------------------------------
    wave_label = _extract_wave_label(sc_1d)
    dow_label = _extract_dow_label(sc_1d)

    return {
        "symbol": symbol,
        "tf": tf,
        "direction": direction,           # 'up' / 'down' / 'side'
        "percent": perc,                  # {'up': .., 'down': .., 'side': ..}
        "entry": entry,
        "stop_loss": sl,
        "take_profits": take_profits,     # {'TP1': .., 'TP2': .., 'TP3': ..}
        "ema50": ema50,
        "ema200": ema200,
        "scenarios": sc_1d,               # เก็บไว้เผื่อใช้งานอื่น
        "recent_high": recent_high,
        "recent_low": recent_low,
        "atr_pct": atrp,
        "wave_label": wave_label,
        "dow_label": dow_label,
        "weekly_bias": weekly_bias,       # เช่น 'DOWN'
    }

# =============================================================================
# LAYER E) FORMATTERS
# -----------------------------------------------------------------------------
def _mark_val(val: Optional[float], current: Optional[float], direction_up: bool, is_sl: bool) -> str:
    """
    คืน string ตัวเลข พร้อม '✅' เมื่อแตะเป้า
    - สำหรับ TP:   Long = current >= val,  Short = current <= val
    - สำหรับ SL:   Long = current <= val,  Short = current >= val
    """
    if val is None:
        return "-"
    if current is None:
        return f"{val:,.2f}"

    if is_sl:
        hit = (current <= val) if direction_up else (current >= val)
    else:
        hit = (current >= val) if direction_up else (current <= val)

    return f"{val:,.2f}" + (" ✅" if hit else "")

# --- (E.1) Short summary -----------------------------------------------------
def format_trade_text(s: Dict[str, object]) -> str:
    sym, tf = s.get("symbol", ""), s.get("tf", "")
    direction = str(s.get("direction", "")).upper()
    perc = s.get("percent", {}) or {}

    entry = s.get("entry")
    sl = s.get("stop_loss")
    tps = s.get("take_profits", {}) or {}
    ema50, ema200 = s.get("ema50"), s.get("ema200")

    direction_up = (direction == "UP")
    current = float(entry) if entry else None

    tp_txts = [
        _mark_val(tps.get("TP1"), current, direction_up, is_sl=False),
        _mark_val(tps.get("TP2"), current, direction_up, is_sl=False),
        _mark_val(tps.get("TP3"), current, direction_up, is_sl=False),
    ]
    sl_txt = _mark_val(sl, current, direction_up, is_sl=True)

    lines = [
        f"{sym} ({tf})",
        f"Direction: {direction}",
        f"ราคา: {entry:,.2f}" if entry else "ราคา: -",
        f"UP {perc.get('up',0)}% | DOWN {perc.get('down',0)}% | SIDE {perc.get('side',0)}%",
    ]
    if ema50 and ema200:
        lines.append(f"EMA50 {ema50:,.2f} / EMA200 {ema200:,.2f}")
    lines.append(f"TP1 {tp_txts[0]} | TP2 {tp_txts[1]} | TP3 {tp_txts[2]}")
    lines.append(f"SL {sl_txt}")
    return "\n".join(lines)

# --- (E.2) Detailed (ตามฟอร์แมตที่คุณต้องการ) -----------------------------
def format_trade_text_detailed(s: Dict[str, object]) -> str:
    sym, tf = s.get("symbol", ""), s.get("tf", "")
    direction_raw = str(s.get("direction", "")).lower()  # 'up'/'down'/'side'
    direction = direction_raw.upper()
    perc = s.get("percent", {}) or {}

    entry = s.get("entry")
    sl = s.get("stop_loss")
    tps = s.get("take_profits", {}) or {}
    ema50, ema200 = s.get("ema50"), s.get("ema200")

    recent_high = s.get("recent_high")
    recent_low = s.get("recent_low")
    wave_label = s.get("wave_label", "Unknown")
    dow_label = s.get("dow_label", "SIDE")
    weekly_bias = s.get("weekly_bias", direction)

    direction_up = (direction == "UP")
    current = float(entry) if entry else None

    tp_txts = [
        _mark_val(tps.get("TP1"), current, direction_up, is_sl=False),
        _mark_val(tps.get("TP2"), current, direction_up, is_sl=False),
        _mark_val(tps.get("TP3"), current, direction_up, is_sl=False),
    ]
    sl_txt = _mark_val(sl, current, direction_up, is_sl=True)

    # เลือก "แผน Breakout" ตามทิศทาง: DOWN=หลุด L, UP=ทะลุ H
    plan_label = "Short – Breakout" if direction == "DOWN" else "Long – Breakout"
    plan_entry = recent_low if direction == "DOWN" else recent_high

    lines = [
        f"{sym} ({tf}) [{weekly_bias} 1W]",
        f"Direction: {direction} ({'Short' if direction=='DOWN' else 'Long'})",
        f"ราคา: {entry:,.2f}" if entry else "ราคา: -",
        f"ความน่าจะเป็น — ขึ้น {perc.get('up',0)}% | ลง {perc.get('down',0)}% | ออกข้าง {perc.get('side',0)}%",
        f"กรอบล่าสุด: H {_fmt(recent_high)} / L {_fmt(recent_low)}",
        f"EMA50 {_fmt(ema50)} / EMA200 {_fmt(ema200)}",
        "TP: 3% / 5% / 7% | SL: 3%",
        "",
        "เหตุผลย่อ:",
        f"• Dow {dow_label}",
        f"• Elliott {wave_label}",
        f"• Weekly context: {weekly_bias} bias",
        "",
        "📌 แผนเทรดที่ระบบเลือก:",
        plan_label,
        f"Entry: {_fmt(plan_entry)}",
        f"TP1 {tp_txts[0]} | TP2 {tp_txts[1]} | TP3 {tp_txts[2]}",
        f"SL {sl_txt}",
    ]
    return "\n".join(lines)
