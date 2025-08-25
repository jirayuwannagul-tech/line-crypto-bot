#!/usr/bin/env python3
"""
Trade Signal Generator
รวมผล Elliott + ราคาจริง Binance + Probabilities จาก scenarios.py
เลือกสัญญาณเดียวตาม % ที่มากที่สุด
"""

from __future__ import annotations

import requests
import pandas as pd
import sys, os
from typing import Dict, Optional, Tuple

# import ฟังก์ชันจากโปรเจกต์
from app.logic.scenarios import analyze_scenarios
from app.analysis.timeframes import get_data

TP_PCTS = [0.03, 0.05, 0.07]
SL_PCT = 0.03

# ===============================
# Utils: ATR% และ Watch Levels
# ===============================
def _atr_pct(df: pd.DataFrame, n: int = 14) -> Optional[float]:
    """
    คำนวณ ATR เป็นสัดส่วนของราคา (เช่น 0.006 = 0.6%)
    """
    if df is None or len(df) < n + 1:
        return None
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    last_close = float(c.iloc[-1])
    if last_close == 0:
        return None
    return float(atr.iloc[-1] / last_close)

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
    buffer_abs = max(pct_buffer * price, atr_mult * atr_pct * price)  (ถ้าไม่มี atr_pct ใช้ pct_buffer อย่างเดียว)
    long_watch  = high + buffer_abs
    short_watch = low  - buffer_abs
    """
    if high is None or low is None:
        return None
    buf_pct_abs = pct_buffer * price
    buf_atr_abs = (atr_mult * atr_pct * price) if (atr_pct is not None and atr_pct > 0) else 0.0
    buffer_abs = max(buf_pct_abs, buf_atr_abs) if buf_atr_abs > 0 else buf_pct_abs
    return (float(high) + buffer_abs, float(low) - buffer_abs, buffer_abs)

# ===============================
# ดึงราคาจริง BTC จาก Binance
# ===============================
def get_btc_price() -> Dict[str, float]:
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=1"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    if not data or (isinstance(data, dict) and "code" in data):
        raise RuntimeError(f"Binance API error: {data}")
    kline = data[0]
    return {
        "open": float(kline[1]),
        "high": float(kline[2]),
        "low": float(kline[3]),
        "close": float(kline[4]),
        "volume": float(kline[5]),
    }

# ===============================
# โหลด Elliott ล่าสุดจาก summary CSV
# ===============================
def load_latest_event(csv_path: str):
    if not os.path.exists(csv_path):
        return None
    df = pd.read_csv(csv_path)
    if df.empty:
        return None
    return df.iloc[-1]

# ===============================
# สร้างแผนเทรด
# ===============================
def build_trade_plan(event, price_info) -> str:
    close = price_info["close"]
    high = price_info["high"]
    low = price_info["low"]

    # Elliott (ถ้าไม่มี event ให้ UNKNOWN)
    elliott_pattern = event["new_pattern"] if event is not None and "new_pattern" in event else "UNKNOWN"
    elliott_stage = event["new_stage"] if event is not None and "new_stage" in event else "UNKNOWN"

    # ===== ใช้ scenarios.py คำนวณ probs จริง =====
    df = get_data("BTCUSDT", "1D")
    probs = analyze_scenarios(df)

    # ---- Normalize probs ----
    probs_simple: Dict[str, float] = {}
    if isinstance(probs, dict):
        # รองรับทั้ง {"up": {"prob": 40}, ...} และ {"up": 40, ...}
        for k, v in probs.items():
            if isinstance(v, dict):
                probs_simple[k] = v.get("prob", 0)
            elif isinstance(v, (int, float)):
                probs_simple[k] = v
    elif isinstance(probs, list):
        # รองรับ [{"dir":"up","prob":40}, ...]
        for item in probs:
            if isinstance(item, dict) and "dir" in item:
                probs_simple[item["dir"]] = item.get("prob", 0)

    if not probs_simple:
        probs_simple = {"up": 0, "down": 0, "side": 0}

    # Weekly bias mock (TODO: ต่อไปคำนวณจริง)
    weekly_bias = "DOWN"

    # Long/Short setup (เปอร์เซ็นต์)
    long_tp = [round(close * (1 + p), 2) for p in TP_PCTS]
    long_sl = round(close * (1 - SL_PCT), 2)
    short_tp = [round(close * (1 - p), 2) for p in TP_PCTS]
    short_sl = round(close * (1 + SL_PCT), 2)

    # หาทางเลือกที่มี % สูงสุด
    bias = max(probs_simple, key=probs_simple.get)

    # ATR% เพื่อใช้ใน watch levels
    atrp = _atr_pct(df, n=14)

    # คำนวณ watch levels จากกรอบล่าสุด (H/L) + buffer
    watch_lines = ""
    wl = suggest_watch_levels(high=high, low=low, price=close, atr_pct=atrp, pct_buffer=0.0025, atr_mult=0.25)
    if wl is not None:
        long_watch, short_watch, buf_abs = wl
        watch_lines = (
            "\n🔎 Watch levels (รอสัญญาณ)"
            f"\n• Long watch ≈ {long_watch:,.2f} (H + buffer)"
            f"\n• Short watch ≈ {short_watch:,.2f} (L - buffer)"
        )

    text = f"""BTCUSDT (1D) [{weekly_bias} 1W]
ราคา: {close:,.2f}
Bias: {bias.upper()} ({probs_simple[bias]}%)
กรอบล่าสุด: H {high:,.2f} / L {low:,.2f}
เหตุผลย่อ:
• Dow SIDE
• Elliott {elliott_pattern} ({elliott_stage})
• Weekly context: {weekly_bias} bias
"""

    if bias == "up":
        text += f"""
📈 Long Setup
Entry: {close:,.2f}
TP1 +3%: {long_tp[0]:,.2f} | TP2 +5%: {long_tp[1]:,.2f} | TP3 +7%: {long_tp[2]:,.2f}
SL −3%: {long_sl:,.2f}
"""
    elif bias == "down":
        text += f"""
📉 Short Setup
Entry: {close:,.2f}
TP1 −3%: {short_tp[0]:,.2f} | TP2 −5%: {short_tp[1]:,.2f} | TP3 −7%: {short_tp[2]:,.2f}
SL +3%: {short_sl:,.2f}
"""
    else:
        text += "\n⚠️ ตลาด Sideway — ยังไม่แนะนำสัญญาณเข้า\n"

    # ต่อท้าย watch levels (ถ้ามี)
    if watch_lines:
        text += f"{watch_lines}\n"

    return text

# ===============================
# Main
# ===============================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backtest/sim_trade_signal.py <events_summary.csv>")
        sys.exit(1)

    events_csv = sys.argv[1]
    event = load_latest_event(events_csv)
    price_info = get_btc_price()

    plan = build_trade_plan(event, price_info)
    print(plan)
