# jobs/push_btc_hourly.py
import asyncio
import pandas as pd
from datetime import datetime

from app.analysis.timeframes import get_data
from app.analysis.scenarios import analyze_scenarios
from app.adapters.line.client import push_text

LINE_TARGET = "YOUR_LINE_USER_ID"  # ตั้งค่าเป็น User ID หรือ Group ID ของคุณ


async def push_btc():
    try:
        # 1) โหลดข้อมูล 1H
        df = get_data("BTCUSDT", "1H")
        if df is None or df.empty:
            raise RuntimeError("No data loaded for BTCUSDT 1H")

        # 2) วิเคราะห์ (แก้เป็น keyword arguments)
        result = analyze_scenarios(df, symbol="BTCUSDT", tf="1H")

        # 3) เตรียมข้อความสรุป
        msg = f"""
BTC 1H Report ({datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC)
Up={result['percent']['up']}% | Down={result['percent']['down']}% | Side={result['percent']['side']}%
EMA50={result['levels']['ema50']:.2f} | EMA200={result['levels']['ema200']:.2f}
Recent High={result['levels']['recent_high']:.2f} | Recent Low={result['levels']['recent_low']:.2f}
        """.strip()

        # 4) ส่งไป LINE
        await push_text(LINE_TARGET, msg)
        print("[OK] pushed BTC report to LINE")

    except Exception as e:
        print("[ERROR]", e)


if __name__ == "__main__":
    asyncio.run(push_btc())
