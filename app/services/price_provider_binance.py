from typing import Optional
from app.utils.crypto_price import fetch_price  # ใช้ wrapper ที่มีหลาย host + fallback

class BinancePriceProvider:
    def get_last_price(self, symbol: str, vs: str = "USDT") -> float:
        price: Optional[float] = fetch_price(symbol, vs)
        if price is None:
            raise RuntimeError(f"Cannot fetch price for {symbol}/{vs}")
        return float(price)
