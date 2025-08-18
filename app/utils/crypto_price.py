import httpx

# สำรองหลายโดเมนของ Binance เผื่อบางตัวล่ม/ถูกบล็อก
BINANCE_BASES = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

async def fetch_price(symbol: str) -> float:
    sym = symbol.upper()
    last_err = None
    for base in BINANCE_BASES:
        url = f"{base}/api/v3/ticker/price"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, params={"symbol": sym})
                r.raise_for_status()
                data = r.json()
                return float(data["price"])
        except Exception as e:
            last_err = e  # เก็บไว้เผื่อดีบัก แล้วลองตัวถัดไป
            continue
    # ทุกฐานล้มเหลว
    raise RuntimeError(f"all binance endpoints failed: {last_err}")

# เผื่อโค้ดเก่ายังเรียกชื่อนี้อยู่
async def fetch_btc_price() -> float:
    return await fetch_price("BTCUSDT")

async def fetch_eth_price() -> float:
    return await fetch_price("ETHUSDT")
