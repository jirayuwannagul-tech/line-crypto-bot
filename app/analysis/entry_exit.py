# app/analysis/entry_exit.py
from __future__ import annotations
from typing import Dict, Optional, Tuple

import math
import pandas as pd

from .scenarios import analyze_scenarios

__all__ = ["suggest_trade", "format_trade_text"]


def _rr(entry: float, sl: float, tp: float) -> Optional[float]:
    """คำนวณ Risk:Reward (R:R). ถ้าข้อมูลไม่ครบ คืน None"""
    if entry is None or sl is None or tp is None:
        return None
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk == 0:
        return None
    return reward / risk


def suggest_trade(
    df: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    สร้างคำแนะนำจุดเข้า/TP/SL จากผล scenarios

    Logic สรุป:
      - เลือกทิศทางจากเปอร์เซ็นต์มากสุด (%up/%down/%side)
      - UP  → Entry=close, SL=recent_low, TP=Fibo extensions (1.272/1.618) ที่ 'สูงกว่า' Entry
      - DOWN→ Entry=close, SL=recent_high, TP=Fibo extensions (1.272/1.618) ที่ 'ต่ำกว่า' Entry
      - ถ้าไม่เจอ TP ที่เหมาะสม → fallback เป็น recent_high/low ตามทิศ
      - รองรับตัวกรองพื้นฐานจาก cfg:
          cfg = {
            "min_prob": 0,          # เปอร์เซ็นต์ขั้นต่ำของทิศที่เลือก (0-100)
            "min_rr": 0.0,          # Risk:Reward ขั้นต่ำ (เช่น 1.5)
          }
    """
    cfg = cfg or {}
    sc = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=cfg.get("sc_cfg", None))
    last = df.iloc[-1]
    close = float(last["close"])

    # เลือกทิศทางหลักจากเปอร์เซ็นต์มากสุด
    perc: Dict[str, int] = sc.get("percent", {"up": 33, "down": 33, "side": 34})
    direction = max(perc, key=perc.get)  # "up" | "down" | "side"

    # เงื่อนไขความเชื่อมั่นขั้นต่ำ (ถ้าตั้งค่า)
    note: Optional[str] = None
    min_prob = float(cfg.get("min_prob", 0))  # 0..100
    if perc.get(direction, 0) < min_prob:
        note = f"Confidence below threshold: {perc.get(direction, 0)}% < {min_prob}%"

    levels = sc.get("levels", {})
    recent_high = levels.get("recent_high")
    recent_low = levels.get("recent_low")
    fibo = levels.get("fibo", {}) or {}
    ext_1272 = fibo.get("ext_1.272")
    ext_1618 = fibo.get("ext_1.618")

    entry: Optional[float] = None
    sl: Optional[float] = None
    take_profits: Dict[str, float] = {}

    if direction == "up":
        entry = close
        sl = float(recent_low) if recent_low is not None else None

        # ใช้ EXTENSIONS ที่สูงกว่า Entry
        candidates: Tuple[Tuple[str, Optional[float]], ...] = (
            ("TP1", ext_1272),
            ("TP2", ext_1618),
        )
        take_profits = {k: float(v) for k, v in candidates if v is not None and v > entry}

        # ถ้าไม่มี TP เหมาะสม → fallback recent_high
        if not take_profits and recent_high is not None and recent_high > entry:
            take_profits = {"TP1": float(recent_high)}

    elif direction == "down":
        entry = close
        sl = float(recent_high) if recent_high is not None else None

        # ใช้ EXTENSIONS ที่ต่ำกว่า Entry
        candidates = (
            ("TP1", ext_1272),
            ("TP2", ext_1618),
        )
        take_profits = {k: float(v) for k, v in candidates if v is not None and v < entry}

        # ถ้าไม่มี TP เหมาะสม → fallback recent_low
        if not take_profits and recent_low is not None and recent_low < entry:
            take_profits = {"TP1": float(recent_low)}
    else:
        # SIDE → ยังไม่แนะนำจุดเข้า
        entry = None
        sl = None
        note = (note + " | " if note else "") + "Market is SIDE (no entry suggested)."

    # กรองตาม R:R ขั้นต่ำ (ถ้าตั้งค่า)
    min_rr = float(cfg.get("min_rr", 0.0))
    if entry is not None and sl is not None and min_rr > 0 and take_profits:
        filtered: Dict[str, float] = {}
        for name, tp in take_profits.items():
            ratio = _rr(entry, sl, tp)
            if ratio is not None and ratio >= min_rr:
                filtered[name] = tp
        if filtered:
            take_profits = filtered
        else:
            # ถ้าไม่มี TP ผ่านเงื่อนไข R:R ให้คง TP เดิมไว้ แต่ใส่หมายเหตุ
            note = (note + " | " if note else "") + f"No TP meets R:R ≥ {min_rr}"

    return {
        "symbol": symbol,
        "tf": tf,
        "direction": direction,                 # "up" | "down" | "side"
        "percent": perc,                        # {"up": int, "down": int, "side": int}
        "entry": entry,                         # float | None
        "stop_loss": sl,                        # float | None
        "take_profits": take_profits,           # {"TP1": float, "TP2": float, ...}
        "note": note,                           # str | None
        "scenarios": sc,                        # แนบผลวิเคราะห์เต็มไว้ใช้งานต่อ
    }


def _fmt(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    # แสดงทศนิยม 2 ตำแหน่งแบบคงที่
    return f"{x:,.2f}"


def format_trade_text(s: Dict[str, object]) -> str:
    """
    แปลงผลลัพธ์จาก suggest_trade() เป็นข้อความสั้นๆ สำหรับตอบใน LINE
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
    tp_list = " / ".join(_fmt(v) for _, v in sorted(tps.items()))

    lines = [
        f"📊 {sym} {tf} — สรุปสัญญาณ",
        f"UP {up_p}% | DOWN {down_p}% | SIDE {side_p}%",
        "",
        f"🎯 ทางเลือก (bias): {direction}",
        f"• Entry: {entry}",
        f"• SL: {sl}",
        f"• TP: {tp_list if tp_list else '-'}",
    ]
    note = s.get("note")
    if note:
        lines += ["", f"ℹ️ {note}"]
    return "\n".join(lines)
