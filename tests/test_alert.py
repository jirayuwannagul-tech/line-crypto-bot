# =============================================================================
# Test Script - ส่งข้อความจริงไป LINE OA
# =============================================================================

import asyncio
from app.adapters.delivery_line import broadcast_message
from app.utils.crypto_price import get_price_text
from app.scheduler.runner import TOP10_SYMBOLS


async def main():
    print("=== 🔎 ดึงราคาล่าสุด Top 10 ===")
    msgs = []
    for sym in TOP10_SYMBOLS:
        text = await get_price_text(sym)
        print(text)
        msgs.append(text)

    print("\n=== 🚨 ส่งข้อความจริงไป LINE OA ===")
    # รวมราคาทั้งหมดเป็นข้อความเดียว (ลดการ call API)
    full_msg = "\n".join(msgs)
    await broadcast_message(full_msg)
    print("✅ ส่งข้อความไป LINE แล้ว")


if __name__ == "__main__":
    asyncio.run(main())
