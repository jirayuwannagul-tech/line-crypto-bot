# app/utils/crypto_price.py
import httpx
from app.config.symbols import COINGECKO_IDS

HEADERS = {"User-Agent": "line-crypto-bot/1.0 (+Render)"}
_client: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=10.0,
            headers=HEADERS,
            follow_redirects=True,
        )
    return _client

async def _coingecko_price(coin_id: str) -> float:
    url = "https://api.coingecko.com/api/v3/simple/price"
    c = await _get_client()
    r = await c.get(url, params={"ids": coin_id, "vs_currencies": "usd"})
    r.raise_for_status()
    data = r.json()
    return float(data[coin_id]["usd"])

def _fmt(p: float) -> str:
    return f"{p:,.2f}" if p >= 1 else f"{p:,.6f}"

async def get_price_text(code: str) -> str:
    """
    ดึงราคาจาก CoinGecko ตาม code เช่น BTC ETH XRP ...
    """
    s = (code or "").upper().strip()
    cid = COINGECKO_IDS.get(s)
    if not cid:
        raise RuntimeError(f"unsupported symbol: {s}")

    p = await _coingecko_price(cid)
    return f"{s}/USD ~ {_fmt(p)}"
