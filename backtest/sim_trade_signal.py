#!/usr/bin/env python3
"""
Trade Signal Generator
รวมผล Elliott + ราคาจริง Binance + Probabilities จาก scenarios.py
เลือกสัญญาณเดียวตาม % ที่มากที่สุด
"""

import requests
import pandas as pd
import sys, os

# import ฟังก์ชันจาก scenarios.py
from app.logic.scenarios import analyze_scenarios
from app.analysis.timeframes import get_data

TP_PCTS = [0.03, 0.05, 0.07]
SL_PCT = 0.03

# ===============================
# ดึงราคาจริง BTC จาก Binance
# ===============================
def get_btc_price():
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=1"
    res = requests.get(url, timeout=10)
    data = res.json()
    if not data or "code" in data:
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
def build_trade_plan(event, price_info):
    close = price_info["close"]
    high = price_info["high"]
    low = price_info["low"]

    # Elliott
    elliott_pattern = event["new_pattern"] if event is not None else "UNKNOWN"
    elliott_stage = event["new_stage"] if event is not None else "UNKNOWN"

    # ===== ใช้ scenarios.py คำนวณ probs จริง =====
    df = get_data("BTCUSDT", "1d")
    probs = analyze_scenarios(df)

    # ---- Normalize probs ----
    probs_simple = {}
    if isinstance(probs, dict):
        # case: {"up": {"prob": 40}, ...} หรือ {"up": 40, ...}
        for k, v in probs.items():
            if isinstance(v, dict):
                probs_simple[k] = v.get("prob", 0)
            elif isinstance(v, (int, float)):
                probs_simple[k] = v
    elif isinstance(probs, list):
        # case: [{"dir":"up","prob":40}, ...]
        for item in probs:
            if isinstance(item, dict) and "dir" in item:
                probs_simple[item["dir"]] = item.get("prob", 0)

    if not probs_simple:
        probs_simple = {"up": 0, "down": 0, "side": 0}

    # Weekly bias mock (จะต่อยอดในอนาคต)
    weekly_bias = "DOWN"

    # Long setup
    long_tp = [round(close * (1+p), 2) for p in TP_PCTS]
    long_sl = round(close * (1 - SL_PCT), 2)

    # Short setup
    short_tp = [round(close * (1-p), 2) for p in TP_PCTS]
    short_sl = round(close * (1 + SL_PCT), 2)

    # หาทางเลือกที่มี % สูงสุด
    bias = max(probs_simple, key=probs_simple.get)

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
