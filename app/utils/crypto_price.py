import httpx

BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price?symbol={symbol}"

# ฟังก์ชันหลัก: ใช้ได้กับทุกเหรียญ
async def fetch_price(symbol: str) -> float:
    sym = symbol.upper()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(BINANCE_TICKER.format(symbol=sym))
        r.raise_for_status()
        data = r.json()
        return float(data["price"])

# ฟังก์ชันย่อย (คงชื่อเดิมไว้ให้โค้ดเก่าไม่พัง)
async def fetch_btc_price() -> float:
    return await fetch_price("BTCUSDT")

async def fetch_eth_price() -> float:
    return await fetch_price("ETHUSDT")
