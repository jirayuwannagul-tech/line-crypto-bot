from typing import Optional, Tuple
from app.utils.crypto_price import (
    fetch_price,
    resolve_symbol_vs_from_text,
)

class BinancePriceProvider:
    def _normalize_pair(self, symbol: str, vs_default: str = "USDT") -> Tuple[str, str]:
        """
        รองรับอินพุตได้หลายแบบ:
          - "BTC"          -> (BTC, USDT)
          - "BTCUSDT"      -> (BTC, USDT)
          - "btc/usdt"     -> (BTC, USDT)
          - "eth usd"      -> (ETH, USD)
        """
        parsed = resolve_symbol_vs_from_text(symbol, default_vs=vs_default)
        if not parsed:
            # ถ้าดูไม่ออก ให้ถือว่าเป็น base ล้วนๆ
            return symbol.upper(), vs_default.upper()
        base, vs = parsed
        return base.upper(), vs.upper()

    def get_last_price(self, symbol: str, vs: str = "USDT") -> float:
        base, q = self._normalize_pair(symbol, vs_default=vs)
        price: Optional[float] = fetch_price(base, q)
        if price is None:
            raise RuntimeError(f"Cannot fetch price for {base}/{q}")
        return float(price)
