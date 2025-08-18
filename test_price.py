import asyncio
from app.utils.crypto_price import get_price_text

async def main():
    for sym in ["BTC", "ETH", "SOL", "HBAR", "ADA"]:
        try:
            price = await get_price_text(sym)
            print(price)
        except Exception as e:
            print(sym, "❌", e)

if __name__ == "__main__":
    asyncio.run(main())
