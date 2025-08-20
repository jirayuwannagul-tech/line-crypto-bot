# app/services/signal_service.py
import pandas as pd
from app.engine.signal_engine import SignalEngine
from app.adapters.price_provider import fetch_spot

engine = SignalEngine()

async def analyze_btc() -> str:
    # 1) ดึงราคาจริง
    price = await fetch_spot("BTC", "USDT")
    if not price:
        return "ไม่สามารถดึงราคาจริงได้"

    # 2) สร้าง DataFrame mock OHLCV
    df = pd.DataFrame({
        "open":  [price*0.99, price*1.01, price*0.995],
        "high":  [price*1.01, price*1.02, price*1.01],
        "low":   [price*0.98, price*0.99, price*0.985],
        "close": [price*1.00, price*1.005, price],
    })

    # 3) วิเคราะห์ด้วย Engine
    result = engine.process_ohlcv("BTCUSDT", df)
    side   = result["side"]
    entry  = result["price"]

    # 4) คำนวณ TP/SL
    if side == "LONG":
        tp1, tp2, tp3 = entry*1.03, entry*1.05, entry*1.07
        sl = entry*0.97
    elif side == "SHORT":
        tp1, tp2, tp3 = entry*0.97, entry*0.95, entry*0.93
        sl = entry*1.03
    else:
        tp1 = tp2 = tp3 = sl = None

    # 5) mock % โอกาสชนะ
    long_chance, short_chance = 65, 35

    # 6) สร้างข้อความตอบกลับ
    reply = f"""
📊 สัญญาณ BTC
ราคาเข้า: {entry:,.0f} USDT
ทิศทาง: {side}

✅ TP1 (+3%): {tp1:,.0f}
✅ TP2 (+5%): {tp2:,.0f}
✅ TP3 (+7%): {tp3:,.0f}
❌ SL (−3%): {sl:,.0f}

📈 ความน่าจะเป็น:
- Long win chance: {long_chance}%
- Short win chance: {short_chance}%

➡️ สรุป: ฝั่ง {side} ได้เปรียบ
    """.strip()

    return reply
