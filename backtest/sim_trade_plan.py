#!/usr/bin/env python3
"""
Trade Plan Generator (Real BTC Price via Binance)
ดึงราคาจริงของ BTC/USDT แบบสด ๆ จาก Binance แล้วสร้างข้อความแผนเทรด
"""

import requests

TP_PCTS = [0.03, 0.05, 0.07]   # +3%, +5%, +7%
SL_PCT = 0.03                  # -3%

def get_btc_price():
    """
    ดึงราคาล่าสุดของ BTCUSDT จาก Binance (1D kline)
    """
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

def build_trade_plan(price_info):
    close = price_info["close"]
    high = price_info["high"]
    low = price_info["low"]

    # TODO: แทน mock ด้วย EMA50/EMA200 จริงจาก historical data
    ema50 = round(close * 1.012, 2)
    ema200 = round(close * 0.915, 2)

    # TODO: เชื่อม scenarios.py เพื่อคำนวณจริง
    probs = {"up": 26, "down": 44, "side": 30}
    weekly_bias = "DOWN"

    # ใช้ low ของวันล่าสุดเป็น anchor สำหรับแผน Short
    entry = low
    tp1 = round(entry * (1 - 0.03), 2)
    tp2 = round(entry * (1 - 0.05), 2)
    tp3 = round(entry * (1 - 0.07), 2)
    sl  = round(entry * (1 + SL_PCT), 2)

    text = f"""BTCUSDT (1D) [{weekly_bias} 1W]
ราคา: {close:,.2f}
ความน่าจะเป็น — ขึ้น {probs['up']}% | ลง {probs['down']}% | ออกข้าง {probs['side']}%
กรอบล่าสุด: H {high:,.2f} / L {low:,.2f}
EMA50 {ema50:,.2f} / EMA200 {ema200:,.2f}
TP: 3% / 5% / 7% | SL: 3%
เหตุผลย่อ:
• Dow SIDE
• Elliott UNKNOWN
• Weekly context: {weekly_bias} bias

แผนเทรดที่แนะนำตอนนี้ (Weekly = {weekly_bias}, 1D bias ขึ้น/ลง/ข้าง = {probs['up']}%/{probs['down']}%/{probs['side']}%)

A) Short – Breakout (ปลอดภัยกว่า)
Entry: หลุด {entry:,.2f}
TP1 −3%: {tp1:,.2f} | TP2 −5%: {tp2:,.2f} | TP3 −7%: {tp3:,.2f}
SL +3%: {sl:,.2f}
"""
    return text

if __name__ == "__main__":
    price_info = get_btc_price()
    print(build_trade_plan(price_info))
