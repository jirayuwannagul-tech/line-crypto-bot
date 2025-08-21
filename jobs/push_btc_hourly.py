# jobs/push_btc_hourly.py
import asyncio
from datetime import datetime

from app.analysis.scenarios import analyze_scenarios
from app.adapters.delivery_line import push_text   # ✅ ใช้ push_text

# 👉 ใส่ LINE USER_ID / GROUP_ID ของคุณ
LINE_TARGET = "<YOUR_LINE_USER_ID>"

async def push_btc():
    try:
        # 1) วิเคราะห์ BTCUSDT (1D timeframe)
        result = analyze_scenarios("BTCUSDT", "1D")

        # 2) แปลงเป็นข้อความ
        msg = f"""
📊 BTCUSDT (1D)
⏰ {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC
EMA20={result['ema20']:.2f} | EMA50={result['ema50']:.2f} | EMA200={result['ema200']:.2f}
RSI14={result['rsi14']:.2f}
MACD={result['macd']:.2f} | Signal={result['signal']:.2f} | Hist={result['hist']:.2f}
Support≈{result['support']:.2f} | Resistance≈{result['resistance']:.2f}
        """

        # 3) ส่งไป LINE (async)
        await push_text(LINE_TARGET, msg.strip())

        print("[OK] pushed BTC report to LINE")

    except Exception as e:
        print("[ERROR]", e)


if __name__ == "__main__":
    asyncio.run(push_btc())
