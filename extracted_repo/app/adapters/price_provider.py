# app/adapters/price_provider.py
from __future__ import annotations

from typing import Optional

# =============================================================================
# LAYER A) เดิม (ยังคงใช้ได้อยู่)  — ใช้ยูทิลเดิมของโปรเจกต์ (async)
# =============================================================================
from app.utils.crypto_price import get_price, get_price_text, get_price_usd

__all__ = [
    # Layer A (legacy async utils)
    "fetch_spot",
    "fetch_spot_text",
    "legacy_get_price_usd",
    # Layer B (ccxt / Binance)
    "get_spot_ccxt",
    "get_spot_text_ccxt",
    "get_spot_ccxt_safe",
    "get_spot_text_ccxt_safe",
]

# ใช้ใน engine (ตัวเลข)
async def fetch_spot(symbol: str, vs: str = "USDT") -> Optional[float]:
    """
    ดึงราคาล่าสุดแบบ async ผ่านยูทิลเดิมของโปรเจกต์
    symbol = 'BTC', vs = 'USDT'  → ได้ราคา BTCUSDT (float) หรือ None
    """
    return await get_price(symbol, vs)

# ใช้ใน LINE (ข้อความ)
async def fetch_spot_text(symbol: str, vs: str = "USDT") -> str:
    """
    ดึงราคาล่าสุดแบบข้อความ (พร้อมฟอร์แมต) ผ่านยูทิลเดิมของโปรเจกต์
    """
    return await get_price_text(symbol, vs)

# สำหรับโค้ดเก่า
async def legacy_get_price_usd(symbol: str) -> Optional[float]:
    """
    ดึงราคาเทียบ USD ผ่านยูทิลเดิม (คงไว้เพื่อความเข้ากันได้ย้อนหลัง)
    """
    return await get_price_usd(symbol)


# =============================================================================
# LAYER B) ใหม่ — เชื่อม Binance API ผ่าน ccxt (synchronous)
# -----------------------------------------------------------------------------
# - ไม่แตะเลเยอร์เดิม
# - เพิ่มฟังก์ชันแบบ sync เหมาะกับสคริปต์หรือจุดที่ไม่ต้อง async
# - มี safe wrapper เผื่อ ccxt ไม่ได้ติดตั้ง หรือ API ล่ม → จะไม่ทำให้แอปล้ม
# =============================================================================

def _normalize_symbol(symbol: str, vs: str | None = None) -> str:
    """
    แปลงรูปแบบสัญลักษณ์ให้เป็นของ ccxt:
      - 'BTCUSDT' → 'BTC/USDT'
      - ('BTC','USDT') → 'BTC/USDT'
      - ถ้าเป็น 'BTC/USDT' อยู่แล้ว → คืนเดิม
    """
    s = (symbol or "").strip().upper()
    if "/" in s:
        return s
    # กรณีส่งมาแบบ pair รวม เช่น BTCUSDT
    if vs is None and len(s) > 3 and s.endswith("USDT"):
        base = s[:-4]
        return f"{base}/USDT"
    if vs:
        return f"{s}/{vs.strip().upper()}"
    # fallback (พยายามเดา)
    return s


# พยายามนำเข้า ccxt; ถ้าไม่มี ให้ fallback แบบปลอดภัย
try:
    import ccxt  # type: ignore

    _exchange = ccxt.binance({
        "enableRateLimit": True,
        "timeout": 10_000,  # ms
    })

    def get_spot_ccxt(symbol: str = "BTC/USDT") -> Optional[float]:
        """
        ดึงราคาล่าสุดจาก Binance spot ผ่าน ccxt (sync)
        ใช้สำหรับงานเร็ว ๆ ที่ไม่ต้อง async
        """
        try:
            pair = _normalize_symbol(symbol)
            ticker = _exchange.fetch_ticker(pair)
            # ticker โครงสร้างทั่วไป: {'last': 12345.6, 'bid': ...}
            return float(ticker["last"]) if "last" in ticker and ticker["last"] is not None else None
        except Exception as e:
            # NOTE: ห้าม raise เพื่อไม่ให้ล้มทั้งระบบในเคสเล็กน้อย เช่น เน็ตสะดุด
            print(f"[price_provider] ccxt error: {e}")
            return None

except Exception as _ccxt_err:
    # ไม่มี ccxt หรือสร้าง exchange ไม่ได้ → ให้ฟังก์ชันคืน None แบบนุ่มนวล
    print(f"[price_provider] ccxt unavailable: {_ccxt_err}")

    def get_spot_ccxt(symbol: str = "BTC/USDT") -> Optional[float]:  # type: ignore[no-redef]
        """
        Fallback เมื่อ ccxt ใช้ไม่ได้: คืน None
        """
        return None


def get_spot_text_ccxt(symbol: str = "BTC/USDT") -> str:
    """
    ดึงราคาล่าสุดจาก Binance spot (ข้อความสำหรับ LINE/Log)
    """
    price = get_spot_ccxt(symbol)
    pair = _normalize_symbol(symbol)
    if price is None:
        return f"ไม่สามารถดึงราคาจาก Binance ได้ ({pair})"
    return f"ราคาล่าสุด {pair} = {price:,.2f} USDT"


# ------------------------------
# Safe wrappers (เผื่ออยากใช้ที่ปลายทาง)
# ------------------------------
def get_spot_ccxt_safe(symbol: str = "BTC/USDT") -> Optional[float]:
    """
    รุ่นปลอดภัย: ถ้าพังจะคืน None (ไม่โยนข้อผิดพลาดออกไป)
    """
    try:
        return get_spot_ccxt(symbol)
    except Exception as e:
        print(f"[price_provider] get_spot_ccxt_safe error: {e}")
        return None


def get_spot_text_ccxt_safe(symbol: str = "BTC/USDT") -> str:
    """
    รุ่นปลอดภัย: คืนข้อความอธิบายผล (ไม่ throw)
    """
    try:
        return get_spot_text_ccxt(symbol)
    except Exception as e:
        pair = _normalize_symbol(symbol)
        return f"ไม่สามารถดึงราคาจาก Binance ได้ ({pair}) — {e}"
