import asyncio
from app.utils.crypto_price import get_price_text

async def main():
    msg = await get_price_text("btc")
    print(msg)

if __name__ == "__main__":
    asyncio.run(main())
