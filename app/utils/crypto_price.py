# app/utils/crypto_price.py
# =============================================================================
# LAYER: UTILS / DATA PROVIDER
#   - ดึงข้อมูลราคา OHLCV จาก CoinGecko (หรือ provider อื่น)
#   - คืนค่าเป็น pandas DataFrame ที่มีคอลัมน์: open, high, low, close, volume
#   - มีฟังก์ชัน get_price_text สำหรับส่งข้อความราคาล่าสุด
# =============================================================================

import httpx
import pandas as pd
from datetime import datetime, timezone


async def fetch_ohlcv(symbol: str, days: int = 1, interval: str = "hourly") -> pd.DataFrame:
    """
    ดึงข้อมูล OHLCV จาก CoinGecko
    :param symbol: เช่น BTC, ETH
    :param days: จำนวนวันที่ต้องการ (1 = 24 ชั่วโมงย้อนหลัง)
    :param interval: "hourly" หรือ "daily"
    """
    url = f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": interval}

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    prices = data.get("prices", [])
    ohlc = []
    for p in prices:
        ts = datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc)
        price = p[1]
        ohlc.append(
            {
                "time": ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.0,  # CoinGecko ไม่มี volume แยกใน endpoint นี้
            }
        )

    df = pd.DataFrame(ohlc)
    return df


async def get_price_text(symbol: str) -> str:
    """
    คืนข้อความราคาล่าสุดของเหรียญที่ต้องการ เช่น "BTC ล่าสุด $29,xxx"
    """
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": symbol.lower(), "vs_currencies": "usd"}

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    price = data.get(symbol.lower(), {}).get("usd")
    if price is None:
        return f"❌ ไม่พบข้อมูลราคา {symbol.upper()}"
    return f"💰 ราคา {symbol.upper()} ล่าสุด: ${price:,.2f} USD"
