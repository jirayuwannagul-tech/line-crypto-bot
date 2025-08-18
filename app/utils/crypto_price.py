import httpx
import asyncio
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

async def _coingecko_price(coin_id: str, retries: int = 3) -> float:
    """
    ดึงราคาจาก CoinGecko พร้อม retry/backoff
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    c = await _get_client()

    for attempt in range(retries):
        try:
            r = await c.get(url, params={"ids": coin_id, "vs_currencies": "usd"})
            r.raise_for_status()
            data = r.json()
            return float(data[coin_id]["usd"])
        except httpx.HTTPStatusError as e:
            # ถ้าเจอ 429 (rate limit) → หน่วงแล้วลองใหม่
            if e.response.status_code == 429 and attempt < retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(1)
                continue
            raise

    raise RuntimeError(f"CoinGecko failed for {coin_id}")

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
