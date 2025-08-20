# =============================================================================
# Test Script - Manual run เพื่อทดสอบการแจ้งเตือน
# ใช้ดึงราคามาแสดง + trigger tick_once()
# =============================================================================

import asyncio
from app.scheduler.runner import tick_once, TOP10_SYMBOLS
from app.utils.crypto_price import get_price_text


async def main():
    print("=== 🔎 ทดสอบดึงราคาปัจจุบัน ===")
    for sym in TOP10_SYMBOLS:
        text = await get_price_text(sym)
        print(text)

    print("\n=== 🚨 ทดสอบ tick_once (dry-run) ===")
    await tick_once(symbols=TOP10_SYMBOLS, dry_run=True)


if __name__ == "__main__":
    asyncio.run(main())
