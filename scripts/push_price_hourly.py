# app/services/price_provider_binance.py
from __future__ import annotations
import os
from typing import Iterable, Optional
import httpx

DEFAULT_HOSTS = (
    os.getenv("BINANCE_HOST", "https://api.binance.com"),
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
)

class BinancePriceProvider:
    def __init__(
        self,
        hosts: Optional[Iterable[str]] = None,
        timeout: float = 10.0,
        retries: int = 3,
    ):
        self.hosts = tuple(hosts) if hosts else DEFAULT_HOSTS
        self.timeout = timeout
        self.retries = max(1, retries)

    def get_last_price(self, symbol: str) -> float:
        """ดึงราคาล่าสุดจาก /api/v3/ticker/price (มี fallback หลายโฮสต์ + retry ภายใน)"""
        params = {"symbol": symbol.upper()}
        last_err: Optional[Exception] = None

        for _ in range(self.retries):
            for host in self.hosts:
                url = f"{host}/api/v3/ticker/price"
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        r = client.get(url, params=params)
                        r.raise_for_status()
                        data = r.json()
                        return float(data["price"])
                except Exception as e:
                    last_err = e
                    continue
        raise RuntimeError(f"Cannot fetch price for {symbol}: {last_err}")
