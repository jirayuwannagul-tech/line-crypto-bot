# jobs/push_btc_hourly.py
import asyncio
import os

from app.services.signal_service import make_trade_signal
from app.adapters.delivery_line import push_text, broadcast_text  # ✅ ใช้ delivery_line

# 👉 ตั้งค่าใน .env ก็ได้ (แนะนำ) หรือจะฮาร์ดโค้ดก็ได้
# LINE_TARGET_USER_ID=Uc6abb9a104a3bc78e6627150c62fb962
LINE_TARGET = os.getenv("LINE_TARGET_USER_ID", "Uc6abb9a104a3bc78e6627150c62fb962")

async def push_btc():
    try:
        # 1) สร้างข้อความตามฟอร์แมตที่ต้องการ (1H)
        msg = make_trade_signal("BTCUSDT", "1H")

        # 2) ส่งไป LINE
        if LINE_TARGET:
            await push_text(LINE_TARGET, msg)
        else:
            await broadcast_text(msg)

        print("[OK] pushed BTC trade signal to LINE")
    except Exception as e:
        print("[ERROR]", e)

if __name__ == "__main__":
    asyncio.run(push_btc())
