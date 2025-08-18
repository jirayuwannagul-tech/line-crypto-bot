import asyncio
from app.utils.crypto_price import get_price_text
from app.config.symbols import COINGECKO_IDS

async def main():
    for sym in COINGECKO_IDS.keys():
        try:
            price = await get_price_text(sym)
            print(price)
        except Exception as e:
            print(sym, "❌", e)

        # กัน rate limit เพิ่มเติม
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
