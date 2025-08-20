# test_alert.py
import asyncio
import logging
from app.utils import state_store
from app.scheduler import runner

logging.basicConfig(level=logging.INFO)

async def main():
    # baseline ของ BTC (สมมุติให้มี)
    state_store.set_baseline("BTC", 10.0)

    # ดึงราคาปัจจุบันของ BTC โดยตรง
    price = await runner._aget_numeric_price("BTC")
    print(f"Current BTC price: {price}")

if __name__ == "__main__":
    asyncio.run(main())
