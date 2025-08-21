# jobs/push_btc_hourly.py
import asyncio
import os

from app.analysis.timeframes import get_data
from app.analysis.scenarios import analyze_scenarios
from app.adapters.line.client import push_text

LINE_TARGET = os.getenv("LINE_TARGET", "")

async def push_btc():
    try:
        # 1) โหลดข้อมูล 1H
        df = get_data("BTCUSDT", "1H")

        # 2) วิเคราะห์
        result = analyze_scenarios(df, symbol="BTCUSDT", tf="1H")

        # 3) สร้างข้อความ
        msg = f"""
BTC/USDT 1H
Up={result['percent']['up']}% | Down={result['percent']['down']}% | Side={result['percent']['side']}%
High≈{result['levels'].get('recent_high')}
Low≈{result['levels'].get('recent_low')}
EMA50≈{result['levels'].get('ema50')}
EMA200≈{result['levels'].get('ema200')}
        """

        # 4) ส่งไป LINE
        await push_text(LINE_TARGET, msg.strip())
        print("[OK] pushed BTC report to LINE")

    except Exception as e:
        print("[ERROR]", e)

if __name__ == "__main__":
    asyncio.run(push_btc())
