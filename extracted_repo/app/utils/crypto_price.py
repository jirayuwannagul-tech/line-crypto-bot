import os
import time
import asyncio
import re
import httpx
from typing import Optional, Dict, Tuple

# =============================================================================
# ENV & DEFAULTS
# =============================================================================
_DEFAULT_VS = os.getenv("QUOTE_ASSET", "USDT").upper()
_PROVIDER   = os.getenv("PRICE_PROVIDER", "binance").lower()  # binance|coingecko
_PRICE_TTL  = int(os.getenv("PRICE_TTL_SECONDS", "15"))
_BINANCE_HOSTS = [
    os.getenv("BINANCE_HOST", "https://api.binance.com"),
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data-api.binance.vision",
]

# สกุลอ้างอิงที่เจอบ่อย (ถ้า user ใส่มาด้วย)
_KNOWN_VS = {"USDT", "USD", "BUSD", "USDC", "BTC", "ETH"}

_price_cache: Dict[str, Tuple[float, float]] = {}


# =============================================================================
# CACHE
# =============================================================================
def _cache_key(symbol: str, vs: str) -> str:
    return f"{symbol.upper()}-{vs.upper()}"

def _get_cached(symbol: str, vs: str) -> Optional[float]:
    row = _price_cache.get(_cache_key(symbol, vs))
    if not row:
        return None
    price, ts = row
    return price if (time.time() - ts) <= _PRICE_TTL else None

def _set_cache(symbol: str, vs: str, price: float) -> None:
    _price_cache[_cache_key(symbol, vs)] = (price, time.time())


# =============================================================================
# PROVIDERS
# =============================================================================
async def _get_price_binance(symbol: str, vs: str) -> Optional[float]:
    """
    ดึงราคาจาก Binance: /api/v3/ticker/price?symbol=BTCUSDT
    symbol = base (BTC), vs = quote (USDT)
    """
    pair = f"{symbol.upper()}{vs.upper()}"
    params = {"symbol": pair}
    headers = {"User-Agent": "line-crypto-bot/1.0"}
    backoffs = [0.5, 1.0]

    for base in _BINANCE_HOSTS:
        url = f"{base.rstrip('/')}/api/v3/ticker/price"
        for wait in [0.0] + backoffs:
            if wait:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(url, params=params, headers=headers)
            except httpx.RequestError:
                continue
            if r.status_code == 200:
                try:
                    j = r.json()
                    return float(j["price"])
                except Exception:
                    break  # response แปลก ๆ ให้ลอง host ถัดไป
            # ถ้า client ส่งคู่ที่ไม่มี 400/404/403/451 ไม่ต้อง retry host เดิม
            if r.status_code in (400, 403, 404, 451):
                break
            if r.status_code == 429:
                # rate limit → ลอง backoff รอบถัดไปได้
                continue
            break
    return None

async def _get_price_coingecko(symbol: str, vs: str) -> Optional[float]:
    """
    ดึงราคาจาก Coingecko แบบ simple price (fallback)
    หมายเหตุ: รองรับเฉพาะเหรียญยอดนิยมตาม SYMBOL_MAP
    """
    vs_currency = "usd" if vs.upper() in ("USD", "USDT") else vs.lower()
    SYMBOL_MAP = {
        "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
        "ADA": "cardano", "XRP": "ripple", "SOL": "solana",
        "DOGE": "dogecoin", "SAND": "the-sandbox",
    }
    coin_id = SYMBOL_MAP.get(symbol.upper())
    if not coin_id:
        return None
    url = "https://api.coingecko.com/api/v3/simple/price"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"ids": coin_id, "vs_currencies": vs_currency})
        if r.status_code != 200:
            return None
        data = r.json()
        val = data.get(coin_id, {}).get(vs_currency)
        return float(val) if val is not None else None
    except Exception:
        return None


# =============================================================================
# CORE PRICE API (ASYNC)
# =============================================================================
async def get_price(symbol: str, vs: str | None = None) -> Optional[float]:
    """
    คืนราคาล่าสุดของคู่ (symbol/vs) เช่น (BTC, USDT) → 12345.67
    """
    vs = (vs or _DEFAULT_VS).upper()
    cached = _get_cached(symbol, vs)
    if cached is not None:
        return cached

    order = [_PROVIDER, "coingecko" if _PROVIDER == "binance" else "binance"]
    price: Optional[float] = None
    for prov in order:
        if prov == "binance":
            price = await _get_price_binance(symbol, vs)
        elif prov == "coingecko":
            price = await _get_price_coingecko(symbol, vs)
        if price is not None:
            break

    if price is not None:
        _set_cache(symbol, vs, price)
    return price

async def get_price_text(symbol: str, vs: str | None = None) -> str:
    """
    เวอร์ชันคืนเป็นข้อความพร้อมหน่วย เช่น "💰 ราคา BTC ล่าสุด: 12,345.67 USD"
    """
    vs = (vs or _DEFAULT_VS).upper()
    price = await get_price(symbol, vs)
    if price is None:
        return f"❌ ไม่พบราคา {symbol.upper()}/{vs}"
    unit = "USD" if vs in ("USD", "USDT") else vs
    return f"💰 ราคา {symbol.upper()} ล่าสุด: {price:,.2f} {unit}"

async def get_price_usd(symbol: str) -> Optional[float]:
    return await get_price(symbol, "USDT")


# =============================================================================
# SYNC WRAPPERS (สำหรับเรียกจากโค้ด synchronous)
# =============================================================================
def _run_async(coro):
    """
    รัน coroutine ให้ปลอดภัยในบริบทที่อาจมี event loop อยู่แล้ว (pytest/fastapi)
    """
    try:
        # ถ้าไม่มี loop ที่กำลังรัน → ใช้ asyncio.run
        return asyncio.run(coro)
    except RuntimeError as e:
        # มี loop กำลังรัน (เช่น ภายใต้ uvicorn/pytest asyncio strict)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # ใช้ task ผ่าน loop แล้วรอด้วย run_until_complete ไม่ได้ → ใช้ helper ผ่าน线程หรือ nest
            # ทางเลือกง่ายและปลอดภัย: ใช้ asyncio.run ใน thread แยก
            import threading
            result_container = {}
            exc_container = {}

            def _worker():
                try:
                    result_container["v"] = asyncio.run(coro)
                except BaseException as ex:
                    exc_container["e"] = ex

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            t.join()
            if "e" in exc_container:
                raise exc_container["e"]
            return result_container.get("v")
        else:
            return loop.run_until_complete(coro)

def fetch_price(symbol: str, vs: str | None = None) -> Optional[float]:
    return _run_async(get_price(symbol, vs))

def fetch_price_text(symbol: str, vs: str | None = None) -> str:
    return _run_async(get_price_text(symbol, vs))


# =============================================================================
# TEXT PARSER & AUTO API
# =============================================================================
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9]{2,20}$")

def _split_pair_token(token: str) -> Tuple[str, Optional[str]]:
    """
    แยก token รูปแบบต่าง ๆ ให้ได้ (base, vs?)
    ตัวอย่าง:
      "BTCUSDT"  -> ("BTC", "USDT")
      "ETHUSD"   -> ("ETH", "USD")
      "ADA"      -> ("ADA", None)       # ไม่มี vs → ให้ไปเติม default ทีหลัง
    เงื่อนไขเรียบง่าย: ถ้า token ลงท้ายด้วย vs ที่เรารู้จัก → ตัดส่วนนั้นเป็น vs
    """
    s = token.upper()
    for vs in sorted(_KNOWN_VS, key=len, reverse=True):  # เช็กตัวที่ยาวก่อน
        if s.endswith(vs) and len(s) > len(vs):
            base = s[: -len(vs)]
            return base, vs
    return s, None

def resolve_symbol_vs_from_text(text: str, default_vs: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """
    รับข้อความอิสระ แล้วพยายามตีความเป็น (symbol, vs)
    รองรับ:
      - "sol" / "btc"                  → (SOL, USDT)
      - "BTCUSDT" / "ETHUSD"           → (BTC, USDT) / (ETH, USD)
      - "btc/usdt", "eth:usdt"         → (BTC, USDT)
      - "ada busd" (มีช่องว่าง)        → (ADA, BUSD)
    คืน None ถ้าดูไม่ออกว่าเป็นสัญลักษณ์
    """
    if not text:
        return None

    default_vs = (default_vs or _DEFAULT_VS).upper()
    t = text.strip().upper()

    # ตัดคั่นกลางทั่วไป
    for sep in ("/", ":", "-", " "):
        if sep in t:
            parts = [p for p in t.replace(sep, " ").split() if p]
            if len(parts) == 1:
                t = parts[0]
                break
            if len(parts) >= 2:
                base = parts[0]
                vs = parts[1]
                if vs not in _KNOWN_VS:
                    return (base, default_vs)
                return (base, vs)

    # กรณีเป็นโทเค็นเดียว
    if _SYMBOL_RE.fullmatch(t):
        base, vs = _split_pair_token(t)  # แยกคู่แบบ BTCUSDT → BTC/USDT
        return (base, vs or default_vs)

    return None

def fetch_price_text_auto(text: str, default_vs: Optional[str] = None) -> str:
    """
    one-call API: ยัดข้อความอะไรมาก็ได้ → คืนราคาที่เหมาะสม
    ใช้กับ input อย่าง "sol", "ethusdt", "btc/usdt", "avax:usdt", "doge"
    """
    parsed = resolve_symbol_vs_from_text(text, default_vs=default_vs)
    if not parsed:
        return "❌ ไม่เข้าใจสัญลักษณ์เหรียญที่ต้องการ กรุณาพิมพ์เช่น: sol, btcusdt, btc/usdt"
    base, vs = parsed
    return fetch_price_text(base, vs)


# =============================================================================
# RESOLVER OBJECT (ให้ tests monkeypatch ได้: price/get/resolve)
# =============================================================================
class _Resolver:
    def get(self, symbol: str) -> Optional[float]:
        return fetch_price(symbol, _DEFAULT_VS)

    def price(self, symbol: str) -> Optional[float]:
        return self.get(symbol)

    def resolve(self, symbol: str) -> Optional[float]:
        return self.get(symbol)

# instance ใช้จริง (tests จะ monkeypatch method ของอ็อบเจ็กต์นี้)
resolver = _Resolver()
