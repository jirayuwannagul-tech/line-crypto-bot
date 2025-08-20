# test_broadcast.py
import asyncio
from app.utils.crypto_price import get_price_text
from app.adapters.delivery_line import broadcast_message


async def main():
    symbols = ["btc", "eth", "doge", "shib", "abcxyz"]
    for sym in symbols:
        try:
            msg = await get_price_text(sym)
        except Exception as e:
            # ดัก error เพื่อไม่ให้ loop หยุด
            msg = f"⚠️ ดึงราคา {sym.upper()} ไม่สำเร็จ ({e.__class__.__name__})"

        # ส่งเข้า LINE
        await broadcast_message(msg)

        # เว้นเวลาเพื่อเลี่ยง rate limit
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())

