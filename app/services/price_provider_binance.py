"""
price_provider_binance.py
=========================

Service สำหรับดึงราคาล่าสุดจาก Binance API
- แยกเป็น Layer: Config / Client / Service
- มี class BinancePriceProvider สำหรับดึงราคาจริง
- มี wrapper get_price() สำหรับ job/service อื่นเรียกง่าย
"""

from __future__ import annotations
import os
from typing import Iterable, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIG LAYER
# =============================================================================
DEFAULT_HOSTS = (
    os.getenv("BINANCE_HOST", "https://api.binance.com"),
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
)
DEFAULT_TIMEOUT = 10.0
DEFAULT_RETRIES = 3


# =============================================================================
# CLIENT LAYER
# =============================================================================
class BinancePriceProvider:
    """Client สำหรับดึงราคาล่าสุดจาก Binance API"""

    def __init__(
        self,
        hosts: Optional[Iterable[str]] = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.hosts = tuple(hosts) if hosts else DEFAULT_HOSTS
        self.timeout = timeout
        self.retries = max(1, retries)

    def get_last_price(self, symbol: str) -> float:
        """
        ดึงราคาล่าสุดจาก Binance API
        return: float
        """
        params = {"symbol": symbol.upper()}
        last_err: Optional[Exception] = None

        for attempt in range(self.retries):
            for host in self.hosts:
                url = f"{host}/api/v3/ticker/price"
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        r = client.get(url, params=params)
                        r.raise_for_status()
                        data = r.json()
                        # ตรวจสอบว่า key มีจริง
                        if "price" not in data:
                            raise ValueError(f"Unexpected response: {data}")
                        return float(data["price"])
                except Exception as e:
                    logger.warning(
                        f"[BinancePriceProvider] attempt={attempt+1} host={host} "
                        f"symbol={symbol} error={e}"
                    )
                    last_err = e
                    continue

        raise RuntimeError(f"Cannot fetch price for {symbol}: {last_err}")


# =============================================================================
# SERVICE LAYER (Wrapper)
# =============================================================================
_provider: Optional[BinancePriceProvider] = None

def get_provider() -> BinancePriceProvider:
    global _provider
    if _provider is None:
        _provider = BinancePriceProvider()
    return _provider


def get_price(symbol: str) -> float:
    """
    Wrapper สำหรับดึงราคาล่าสุด
    ใช้ใน jobs/watch_targets.py และ service อื่น ๆ
    """
    provider = get_provider()
    return provider.get_last_price(symbol)


# =============================================================================
# DEBUG / TEST
# =============================================================================
if __name__ == "__main__":
    try:
        price = get_price("BTCUSDT")
        print(f"BTCUSDT last price = {price}")
    except Exception as e:
        print("Error fetching BTCUSDT:", e)
