# test_alert.py
import asyncio
import httpx

SYMBOL_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "ETC": "ethereum-classic",
}

async def get_price(symbol: str) -> float:
    coin_id = SYMBOL_MAP[symbol]
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        return data[coin_id]["usd"]

async def main():
    for sym in ["BTC", "ETC"]:
        price = await get_price(sym)
        print(f"{sym}: {price} USD")

if __name__ == "__main__":
    asyncio.run(main())
