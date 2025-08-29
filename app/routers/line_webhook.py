# app/routers/line_webhook.py
# =============================================================================
# LINE Webhook Router
# -----------------------------------------------------------------------------
# - รับ Webhook จาก LINE Messaging API
# - รองรับ:
#     • ราคา <symbol>     (เช่น "ราคา btc", "ราคา eth")
#     • พิมพ์สัญลักษณ์   (เช่น "btc", "eth", "BTC/USDT")
#     • ข้อความอิสระเพื่อ "วิเคราะห์แบบเรียลไทม์"
#         ตัวอย่าง: "วิเคราะห์ btc 1h", "btc h1", "analyze eth 4H", "xrp 1D"
# - เก็บ userId ล่าสุด และมีเอ็นด์พอยต์ /debug/* สำหรับทดสอบ push
# - background loop แจ้งข่าว mock ทุก NEWS_PUSH_EVERY_SEC วินาที (ค่า env)
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, Optional
import os
import re
import logging
import asyncio
import datetime as _dt
import string

from fastapi import APIRouter, Request, HTTPException
import httpx

# ---- Internal layers
from app.adapters import price_provider
from app.features.replies.keyword_reply import get_reply  # keyword layer
from app.services.wave_service import analyze_wave, build_brief_message  # วิเคราะห์สด

router = APIRouter()
log = logging.getLogger(__name__)

# เก็บ userId ล่าสุดไว้สำหรับ push ทดสอบ
_last_user_id: Optional[str] = None
# fallback จาก .env (เช่น LINE_USER_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)
_ENV_USER_ID = os.getenv("LINE_USER_ID", "").strip()

# interval สำหรับ push ข่าว mock (วินาที)
_NEWS_INTERVAL = int(os.getenv("NEWS_PUSH_EVERY_SEC", "0"))
_news_task: Optional[asyncio.Task] = None

# =============================================================================
# Helpers
# =============================================================================
def _ascii_token_from_env() -> str:
    """
    ดึง LINE_CHANNEL_ACCESS_TOKEN แล้ว 'ล้าง' ให้เหลือ ASCII 7-bit เท่านั้น
    กันกรณีมี zero-width/emoji/BOM หลุดเข้ามา → httpx จะไม่พังที่ normalize_header_value
    """
    raw = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "") or ""
    cleaned = "".join(ch for ch in raw if ch in string.printable and ord(ch) < 128).strip()
    return cleaned

# =============================================================================
# LINE reply helper
# =============================================================================
async def _reply_text(reply_token: str, text: str) -> None:
    token = _ascii_token_from_env()
    if not token:
        raise HTTPException(status_code=400, detail="LINE_CHANNEL_ACCESS_TOKEN is missing")

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, headers=headers, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=500, detail=f"LINE reply failed: {e.response.text}")

# =============================================================================
# LINE push helper
# =============================================================================
async def _push_text(user_id: str, text: str) -> None:
    token = _ascii_token_from_env()
    if not token:
        raise HTTPException(status_code=400, detail="LINE_CHANNEL_ACCESS_TOKEN is missing")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, headers=headers, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=500, detail=f"LINE push failed: {e.response.text}")

# =============================================================================
# Background news loop
# =============================================================================
async def _news_loop():
    if _NEWS_INTERVAL <= 0:
        return
    while True:
        try:
            await asyncio.sleep(_NEWS_INTERVAL)
            uid = _last_user_id or _ENV_USER_ID
            if uid:
                now = _dt.datetime.now().strftime("%H:%M:%S")
                text = f"📰 ข่าวทดสอบ {now} — ระบบแจ้งเตือนทำงานจริง"
                await _push_text(uid, text)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.exception("news loop error: %s", e)

async def start_news_loop():
    global _news_task
    if _NEWS_INTERVAL > 0 and (_news_task is None or _news_task.done()):
        _news_task = asyncio.create_task(_news_loop())
        log.info("news loop started (interval=%ss)", _NEWS_INTERVAL)

async def stop_news_loop():
    global _news_task
    if _news_task and not _news_task.done():
        _news_task.cancel()
        try:
            await _news_task
        except asyncio.CancelledError:
            pass
        log.info("news loop stopped")

# =============================================================================
# COMMAND PARSER (freeform → symbol/tf แบบยืดหยุ่น)
# =============================================================================
_ALLOWED_TF = {"1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W"}
_SYMBOL_MAP = {
    "btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT",
    "ada": "ADAUSDT", "doge": "DOGEUSDT", "bnb": "BNBUSDT", "sand": "SANDUSDT",
}

def _norm_tf_token(tok: str) -> str:
    """
    รองรับ h1→1H, m15→15M, d1→1D, 4h→4H, 30m→30M รวมถึง '1h','15m','1d','1w'
    """
    t = (tok or "").strip().lower()
    t = (t.replace("minutes", "m").replace("minute", "m").replace("mins", "m").replace("min", "m")
           .replace("hours", "h").replace("hour", "h").replace("hr", "h")
           .replace("daily", "d").replace("day", "d").replace("week", "w").replace("weekly", "w"))
    if t and t[0] in "mhdw" and t[1:].isdigit():
        t = t[1:] + t[0]      # h1 -> 1h, m15 -> 15m, d1 -> 1d
    t = t.upper()
    if t in _ALLOWED_TF:
        return t
    m = re.match(r"^(\d+)\s*([MHDW])$", t)
    if m:
        cand = f"{m.group(1)}{m.group(2)}"
        if cand in _ALLOWED_TF:
            return cand
    return ""

def _parse_symbol_tf_freeform(text: str) -> Dict[str, str]:
    """
    ดึง symbol/tf จากข้อความอิสระ:
      - 'วิเคราะห์ btc 1h', 'btc h1', 'analyze eth 4H', 'xrp 1D', 'doge d1'
      - ถ้าไม่เจอ tf -> 1D, ถ้าไม่เจอ symbol -> BTCUSDT
    """
    s = (text or "").strip().lower()

    # --- symbol ---
    symbol = "BTCUSDT"
    # รองรับรูปแบบ BTC/USDT, BTC-USDT, BTC:USDT
    m_pair = re.search(r"\b([a-z]{3,5})\s*[/\-\:]\s*([a-z]{3,5})\b", s, flags=re.I)
    if m_pair:
        symbol = f"{m_pair.group(1)}{m_pair.group(2)}".upper()
    else:
        for k, v in _SYMBOL_MAP.items():
            if re.search(rf"\b{k}\b", s):
                symbol = v
                break

    # --- timeframe ---
    tf = "1D"
    tokens = re.findall(r"(?:\d+\s*[mhdw]|[mhdw]\s*\d+|\d+\s*[MHDW])", s)
    for tok in tokens:
        tf_norm = _norm_tf_token(tok)
        if tf_norm:
            tf = tf_norm
            break

    return {"symbol": symbol, "tf": tf}

# =============================================================================
# WEBHOOK HANDLER
# =============================================================================
@router.post("/webhook")
async def line_webhook(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = (body or {}).get("events", [])
    if not events:
        return {"ok": True}

    for ev in events:
        try:
            if ev.get("type") != "message":
                continue
            msg = ev.get("message", {})
            if msg.get("type") != "text":
                continue

            # บันทึก userId ล่าสุด (สำหรับ push)
            src = ev.get("source", {}) or {}
            global _last_user_id
            _last_user_id = src.get("userId") or _last_user_id

            user_text = (msg.get("text") or "").strip()
            reply_text: Optional[str] = None

            # 1) ราคา: "ราคา <symbol>"
            if user_text.lower().startswith("ราคา"):
                parts = user_text.split(maxsplit=1)
                if len(parts) >= 2:
                    reply_text = price_provider.get_spot_text_ccxt(parts[1])
                else:
                    reply_text = price_provider.get_spot_text_ccxt("BTCUSDT")

            # 2) พิมพ์สัญลักษณ์เหรียญตรง ๆ → ตอบราคา
            if not reply_text and re.fullmatch(r"[A-Za-z0-9:/\- ]{2,20}", user_text):
                reply_text = price_provider.get_spot_text_ccxt(user_text)

            # 3) keyword ปกติ
            if not reply_text:
                reply_text = get_reply(user_text)

            # 4) วิเคราะห์ "เรียลไทม์" จากข้อความอิสระ (ไม่พึ่งคีย์เวิร์ดคงที่)
            if not reply_text:
                args = _parse_symbol_tf_freeform(user_text)
                symbol, tf = args["symbol"], args["tf"]

                cfg = {"use_live": True, "live_limit": 500}   # ดึงแท่งสดจาก provider (ccxt/binance)
                payload = analyze_wave(symbol, tf, cfg=cfg)
                reply_text = build_brief_message(payload)[:1800]

            # ส่งกลับ
            reply_token = ev.get("replyToken")
            if reply_token and reply_text:
                await _reply_text(reply_token, reply_text)

        except Exception as e:
            log.exception("LINE webhook event error: %s", e)

    return {"ok": True}

# =============================================================================
# DEBUG endpoints
# =============================================================================
@router.get("/debug/whoami")
async def debug_whoami() -> Dict[str, Any]:
    return {
        "last_user_id": _last_user_id,
        "env_user_id": _ENV_USER_ID,
        "using": "last" if _last_user_id else ("env" if _ENV_USER_ID else None),
    }

@router.post("/debug/set_user")
async def debug_set_user(request: Request) -> Dict[str, Any]:
    global _last_user_id
    body = await request.json()
    user_id = (body or {}).get("user_id", "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="ต้องระบุ user_id")
    _last_user_id = user_id
    return {"ok": True, "last_user_id": _last_user_id}

@router.post("/debug/push_news")
async def debug_push_news(request: Request) -> Dict[str, Any]:
    body = await request.json()
    text = (body or {}).get("text", "📰 ข่าวทดสอบ: ระบบ push พร้อมใช้งาน")
    uid = _last_user_id or _ENV_USER_ID
    if not uid:
        raise HTTPException(status_code=400, detail="ยังไม่พบ userId — ส่งข้อความหาบอทก่อน หรือกำหนด LINE_USER_ID ใน .env")
    await _push_text(uid, text)
    return {"ok": True, "pushed_to": uid, "source": "last" if _last_user_id else "env"}

# =============================================================================
# Backward-compat shim for tests: provide line_bot_api with reply_message()
# =============================================================================
class _LineAPINoop:
    def reply_message(self, *args, **kwargs):
        return None
    def push_message(self, *args, **kwargs):
        return None
    def broadcast(self, *args, **kwargs):
        return None

# ให้ tests สามารถ monkeypatch ได้: tests จะทำ monkeypatch.setattr(lw, "line_bot_api", ...)
line_bot_api = _LineAPINoop()
