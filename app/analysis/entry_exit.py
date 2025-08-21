# app/analysis/entry_exit.py
from __future__ import annotations
from typing import Dict, Optional, Tuple, List

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


def _fmt(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    return f"{x:,.2f}"


def suggest_trade(
    df: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    สร้างคำแนะนำจุดเข้า/TP/SL จากผล scenarios

    ค่า config ที่รองรับ:
      - use_pct_targets: bool            # ใช้ SL/TP แบบเปอร์เซ็นต์จาก Entry (ค่าเริ่มต้น False)
      - sl_pct: float                    # % SL เช่น 0.03 = 3%
      - tp_pcts: List[float]             # % TP เช่น [0.03, 0.07, 0.12]
      - min_prob: float                  # กรองขั้นต่ำเชิงความน่าจะเป็นของทิศทางที่เลือก (0-100)
      - min_rr: float                    # กรอง R:R ขั้นต่ำ (เช่น 1.5)
      - sc_cfg: Dict                     # config ส่งต่อไปยัง analyze_scenarios
    """
    cfg = cfg or {}

    sc = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=cfg.get("sc_cfg", None))
    last = df.iloc[-1]
    close = float(last["close"])

    perc: Dict[str, int] = sc.get("percent", {"up": 33, "down": 33, "side": 34})
    # รายงานเปอร์เซ็นต์ขาขึ้น/ขาลงชัดเจน
    prob_up = int(perc.get("up", 0))
    prob_down = int(perc.get("down", 0))
    prob_side = int(perc.get("side", 0))

    # เลือกทิศทางหลักจากเปอร์เซ็นต์มากสุด
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

    # ค่าตั้งต้นสำหรับโหมดเปอร์เซ็นต์
    use_pct_targets = bool(cfg.get("use_pct_targets", False))
    sl_pct = float(cfg.get("sl_pct", 0.03))          # 3% เริ่มต้น
    tp_pcts: List[float] = list(cfg.get("tp_pcts", [0.03, 0.07, 0.12]))  # 3%,7%,12% เริ่มต้น

    entry: Optional[float] = None
    sl: Optional[float] = None
    take_profits: Dict[str, float] = {}

    # ====== ตรรกะหลัก ======
    if direction == "side":
        entry = None
        sl = None
        note = (note + " | " if note else "") + "Market is SIDE (no entry suggested)."
    else:
        entry = close
        if use_pct_targets:
            # โหมดกำหนด SL/TP เป็นเปอร์เซ็นต์จาก Entry ตามที่ผู้ใช้ต้องการ
            if direction == "up":
                sl = entry * (1 - sl_pct)
                # TP ด้านบน
                tps = [entry * (1 + p) for p in tp_pcts]
            else:  # "down"
                sl = entry * (1 + sl_pct)
                # TP ด้านล่าง
                tps = [entry * (1 - p) for p in tp_pcts]
            # กำหนดชื่อ TP1/TP2/TP3
            take_profits = {f"TP{i+1}": float(tp) for i, tp in enumerate(tps)}
        else:
            # โหมดเดิม: ใช้ recent high/low และ Fibonacci extensions
            if direction == "up":
                sl = float(recent_low) if recent_low is not None else None
                candidates: Tuple[Tuple[str, Optional[float]], ...] = (
                    ("TP1", ext_1272),
                    ("TP2", ext_1618),
                )
                take_profits = {k: float(v) for k, v in candidates if v is not None and v > entry}
                if not take_profits and recent_high is not None and recent_high > entry:
                    take_profits = {"TP1": float(recent_high)}
            else:  # "down"
                sl = float(recent_high) if recent_high is not None else None
                candidates = (
                    ("TP1", ext_1272),
                    ("TP2", ext_1618),
                )
                take_profits = {k: float(v) for k, v in candidates if v is not None and v < entry}
                if not take_profits and recent_low is not None and recent_low < entry:
                    take_profits = {"TP1": float(recent_low)}

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
            note = (note + " | " if note else "") + f"No TP meets R:R ≥ {min_rr}"

    return {
        "symbol": symbol,
        "tf": tf,
        "direction": direction,                 # "up" | "down" | "side"
        "percent": perc,                        # {"up": int, "down": int, "side": int}
        "prob_up": prob_up,
        "prob_down": prob_down,
        "entry": entry,                         # float | None
        "stop_loss": sl,                        # float | None
        "take_profits": take_profits,           # {"TP1": float, "TP2": float, "TP3": float}
        "note": note,                           # str | None
        "scenarios": sc,                        # แนบผลวิเคราะห์เต็มไว้ใช้งานต่อ
        "config_used": {
            "use_pct_targets": use_pct_targets,
            "sl_pct": sl_pct,
            "tp_pcts": tp_pcts,
            "min_prob": min_prob,
            "min_rr": min_rr,
        },
    }


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
