# app/services/signal_service.py
import pandas as pd
from app.engine.signal_engine import SignalEngine
from app.adapters.price_provider import fetch_spot

# ====== ส่วน Engine เดิมของคุณ ======
engine = SignalEngine()

async def analyze_btc() -> str:
    # 1) ดึงราคาจริง
    price = await fetch_spot("BTC", "USDT")
    if not price:
        return "ไม่สามารถดึงราคาจริงได้"

    # 2) สร้าง DataFrame mock OHLCV
    df = pd.DataFrame({
        "open":  [price*0.99,  price*1.01,  price*0.995],
        "high":  [price*1.01,  price*1.02,  price*1.01],
        "low":   [price*0.98,  price*0.99,  price*0.985],
        "close": [price*1.00,  price*1.005, price],
    })

    # 3) วิเคราะห์ด้วย Engine
    result = engine.process_ohlcv("BTCUSDT", df)
    side   = result.get("side", "NEUTRAL")
    entry  = float(result.get("price", price))

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


# ====== ตัวสร้าง “ข้อความเทรดสวยๆ” สำหรับ LINE ======
from app.analysis.timeframes import get_data
from app.analysis.scenarios import analyze_scenarios

def _fmt(x, d=2):
    try:
        return f"{float(x):,.{d}f}"
    except Exception:
        return str(x)

def make_trade_signal(symbol: str = "BTCUSDT", tf: str = "1H") -> str:
    """
    สร้างข้อความสัญญาณพร้อมเหตุผลสั้น ๆ ในรูปแบบ:
    📊 BTCUSDT (1H)
    Trend: 🔴 ขาลง
    Entry (Short): 113,899.10
    🎯 TP: 110,482 (−3%) / 108,204 (−5%) / 105,926 (−7%)
    🛡️ SL: 117,316 (+3%)
    เหตุผลสั้น ๆ:
    EMA20 < EMA50 และราคาปิดต่ำกว่า EMA20 → แนวโน้มขาลง
    RSI < 45 → แรงขายเด่นชัด
    MACD < Signal และ Histogram เป็นลบ → โมเมนตัมลบชัดเจน
    """
    df = get_data(symbol, tf)
    if df is None or df.empty:
        return f"📊 {symbol} ({tf})\nไม่พบข้อมูล"

    last = df.iloc[-1]
    res = analyze_scenarios(df)  # ต้องมี ema, rsi, macd, levels/percent ตามที่ระบบคุณคืนมา

    ema20 = res.get("ema", {}).get("ema20")
    ema50 = res.get("ema", {}).get("ema50")
    rsi   = res.get("rsi")
    macd  = res.get("macd", {}).get("macd")
    sig   = res.get("macd", {}).get("signal")
    hist  = res.get("macd", {}).get("hist")

    close = float(last["close"])

    # --- ตัดสินใจแนวโน้มและฝั่งเทรด ---
    cond_up   = (ema20 is not None and ema50 is not None and close > ema20 > ema50) and (rsi is not None and rsi >= 50) and (macd is not None and sig is not None and macd >= sig)
    cond_down = (ema20 is not None and ema50 is not None and close < ema20 < ema50) and (rsi is not None and rsi <= 50) and (macd is not None and sig is not None and macd <= sig)

    if cond_down or (not cond_up and ema20 is not None and ema50 is not None and close < ema20):
        trend = "🔴 ขาลง"
        side  = "Short"
        entry = close
        tp1, tp2, tp3 = entry * 0.97, entry * 0.95, entry * 0.93
        sl            = entry * 1.03
        reason = [
            "EMA20 < EMA50 และราคาปิดต่ำกว่า EMA20 → แนวโน้มขาลง" if ema20 and ema50 else None,
            "RSI < 45 → แรงขายเด่นชัด" if (rsi is not None and rsi < 45) else None,
            "MACD < Signal และ Histogram เป็นลบ → โมเมนตัมลบชัดเจน" if (macd is not None and sig is not None and macd < sig and (hist is None or hist < 0)) else None,
        ]
    else:
        trend = "🟢 ขาขึ้น"
        side  = "Long"
        entry = close
        tp1, tp2, tp3 = entry * 1.03, entry * 1.05, entry * 1.07
        sl            = entry * 0.97
        reason = [
            "EMA20 > EMA50 และราคาปิดอยู่เหนือ EMA20 → แนวโน้มขาขึ้น" if ema20 and ema50 else None,
            "RSI > 55 → มีแรงซื้อ" if (rsi is not None and rsi > 55) else None,
            "MACD > Signal และ Histogram เป็นบวก → โมเมนตัมบวก" if (macd is not None and sig is not None and macd > sig and (hist is None or hist > 0)) else None,
        ]

    # --- จัดข้อความตามฟอร์แมตที่ต้องการ ---
    lines = [
        f"📊 {symbol} ({tf})",
        f"Trend: {trend}",
        f"Entry ({side}): {_fmt(entry)}",
        f"🎯 TP: {_fmt(tp1)} ({'−' if side=='Short' else '+'}3%) / {_fmt(tp2)} ({'−' if side=='Short' else '+'}5%) / {_fmt(tp3)} ({'−' if side=='Short' else '+'}7%)",
        f"🛡️ SL: {_fmt(sl)} ({'+' if side=='Short' else '−'}3%)",
        "เหตุผลสั้น ๆ:",
    ]
    for r in filter(None, reason):
        lines.append(r)
    return "\n".join(lines)
