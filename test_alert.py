# test_alert.py
import asyncio
import logging

from app.scheduler import runner
from app.utils import state_store   # ✅ เปลี่ยนเป็น utils แทน adapters

logging.basicConfig(level=logging.INFO)

async def main():
    # baseline BTC สมมุติราคาไว้ก่อน (จะถูกทับด้วยราคาจริง)
    state_store.set_baseline("BTC", 10.0)

    # รัน tick 1 รอบเพื่อเทสต์ BTC
    await runner.tick_once("BTC")

if __name__ == "__main__":
    asyncio.run(main())
