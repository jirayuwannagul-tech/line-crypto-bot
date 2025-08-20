# app/utils/crypto_price.py
# รองรับ "ทุกเหรียญ" จาก CoinGecko + แคช + retry + resolve ซ้ำชื่อด้วย market cap
# ปรับการแสดงทศนิยมแบบอัตโนมัติ (เหรียญราคาต่ำจะแสดงทศนิยมมากขึ้น)

import time
import asyncio
from typing import Dict, List, Optional
import httpx

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
SYMBOL_TTL_SEC = 6 * 60 * 60     # 6 ชั่วโมงสำหรับรายการเหรียญ
PRICE_TTL_SEC  = 10              # 10 วินาทีสำหรับราคา

class SymbolResolver:
    def __init__(self):
        self._symbol_map: Dict[str, List[str]] = {}   # "btc" -> ["bitcoin", ...]
        self._last_loaded: float = 0.0

    async def _fetch_all_coins(self) -> List[dict]:
        url = f"{COINGECKO_BASE}/coins/list?include_platform=false"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()

    async def refresh(self, force: bool = False):
        if not force and (time.time() - self._last_loaded) < SYMBOL_TTL_SEC:
            return
        coins = await self._fetch_all_coins()
        m: Dict[str, List[str]] = {}
        for c in coins:
            sym = str(c.get("symbol", "")).lower().strip()
            cid = str(c.get("id", "")).strip()
            if not sym or not cid:
                continue
            m.setdefault(sym, []).append(cid)
        self._symbol_map = m
        self._last_loaded = time.time()

    async def resolve_id(self, symbol: str) -> Optional[str]:
        """
        คืนค่า coin_id จาก symbol (ไม่สนตัวพิมพ์)
        ถ้าชนหลาย id → เลือกตัวที่ market cap สูงสุด
        """
        await self.refresh()
        ids = self._symbol_map.get(symbol.lower())
        if not ids:
            return None
        if len(ids) == 1:
            return ids[0]

        # กรณีชื่อซ้ำหลายตัว → ใช้ /coins/markets เลือก market cap สูงสุด
        ids_param = ",".join(ids[:250])
        url = f"{COINGECKO_BASE}/coins/markets?vs_currency=usd&ids={ids_param}"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        if not data:
            return ids[0]
        data.sort(key=lambda x: (x.get("market_cap") or 0), reverse=True)
        return data[0].get("id")

resolver = SymbolResolver()

# ===== ราคา + แคชสั้น ๆ + retry =====
_price_cache: Dict[str, Dict[str, float]] = {}  # coin_id -> {"price": float, "ts": epoch}

async def _fetch_price_usd(coin_id: str) -> Optional[float]:
    url = f"{COINGECKO_BASE}/simple/price?ids={coin_id}&vs_currencies=usd"
    for attempt in range(3):  # retry 3 ครั้ง
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
            row = data.get(coin_id)
            if row and "usd" in row:
                return float(row["usd"])
        except Exception:
            # backoff เล็กน้อยแล้วลองใหม่
            if attempt < 2:
                await asyncio.sleep(0.4 * (attempt + 1))
            else:
                raise
    return None

async def get_price_usd(symbol: str) -> Optional[float]:
    coin_id = await resolver.resolve_id(symbol)
    if not coin_id:
        return None
    now = time.time()
    node = _price_cache.get(coin_id)
    if node and (now - node["ts"] < PRICE_TTL_SEC):
        return node["price"]
    price = await _fetch_price_usd(coin_id)
    if price is not None:
        _price_cache[coin_id] = {"price": price, "ts": now}
    return price

# ===== ฟังก์ชันฟอร์แมตราคา (กำหนดทศนิยมอัตโนมัติ) =====
def _format_price_auto(price: float) -> str:
    """
    กำหนดจำนวนทศนิยมตามช่วงราคา:
      - >= 1,000         → 2 ตำแหน่ง
      - >= 1             → 2 ตำแหน่ง
      - >= 0.1           → 4 ตำแหน่ง
      - >= 0.01          → 5 ตำแหน่ง
      - >= 0.001         → 6 ตำแหน่ง
      - อื่น ๆ (เล็กมาก) → 8 ตำแหน่ง
    """
    if price >= 1000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:,.2f}"
    if price >= 0.1:
        return f"{price:,.4f}"
    if price >= 0.01:
        return f"{price:,.5f}"
    if price >= 0.001:
        return f"{price:,.6f}"
    return f"{price:,.8f}"

async def get_price_text(symbol: str) -> str:
    price = await get_price_usd(symbol)
    if price is None:
        return f"❌ ไม่พบเหรียญ '{symbol.upper()}' บน CoinGecko"
    price_str = _format_price_auto(price)
    return f"💰 ราคา {symbol.upper()} ล่าสุด: {price_str} USD"
