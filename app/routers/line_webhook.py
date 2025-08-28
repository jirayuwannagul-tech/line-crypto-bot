# app/routers/line_webhook.py
# =============================================================================
# LINE Webhook Router
# -----------------------------------------------------------------------------
# - รับ Webhook จาก LINE Messaging API
# - รองรับ keyword reply, ราคา <symbol>, analyze, และพิมพ์สัญลักษณ์เหรียญตรง ๆ (BTC/ETH/...)
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, Optional
import os
import re
import logging

from fastapi import APIRouter, Request, HTTPException
import httpx

# ---- Internal layers
from app.engine.signal_engine import build_line_text          # วิเคราะห์สัญญาณ
from app.utils.crypto_price import fetch_price_text_auto      # ✅ ใช้ auto parser
from app.features.replies.keyword_reply import get_reply      # keyword layer

router = APIRouter()
log = logging.getLogger(__name__)

# =============================================================================
# LINE reply helper (no external client)
# =============================================================================
async def _reply_text(reply_token: str, text: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        raise HTTPException(status_code=400, detail="LINE_CHANNEL_ACCESS_TOKEN is missing")
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:5000]}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, headers=headers, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=500, detail=f"LINE reply failed: {e.response.text}")

# =============================================================================
# COMMAND PARSER
# =============================================================================
_SYM_RE = r"[A-Z0-9:\-/]{3,20}"

def _parse_text(text: str) -> Dict[str, str]:
    """
    พาร์สคำสั่งวิเคราะห์:
      - "analyze <symbol> <TF>"
      - "<symbol> <TF>"
    คืน {"symbol","tf","profile"}
    """
    t = (text or "").strip()
    t_upper = t.upper()

    symbol = "BTCUSDT"
    tf = "1D"
    profile = "baseline"

    # โปรไฟล์ (ออปชัน)  e.g. profile:aggressive
    m_prof = re.search(r"profile:([a-zA-Z0-9_\-]+)", t, flags=re.IGNORECASE)
    if m_prof:
        profile = m_prof.group(1).strip()

    # analyze <sym> <tf>
    m1 = re.search(rf"\banalyze\s+({_SYM_RE})\s+([0-9]+[HDW])\b", t_upper)
    if m1:
        symbol = m1.group(1).upper()
        tf = m1.group(2).upper()
        return {"symbol": symbol, "tf": tf, "profile": profile}

    # <sym> <tf>
    m2 = re.search(rf"\b({_SYM_RE})\s+([0-9]+[HDW])\b", t_upper)
    if m2:
        symbol = m2.group(1).upper()
        tf = m2.group(2).upper()
        return {"symbol": symbol, "tf": tf, "profile": profile}

    return {"symbol": symbol, "tf": tf, "profile": profile}

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

            user_text = (msg.get("text") or "").strip()
            reply_text: Optional[str] = None

            # (1) keyword replies (เช่น สวัสดี, mock, btc ฯลฯ)
            reply_text = get_reply(user_text)

            # (2) keyword ราคาล่าสุด: "ราคา <symbol>"
            if not reply_text and user_text.lower().startswith("ราคา"):
                parts = user_text.split(maxsplit=1)
                if len(parts) >= 2:
                    reply_text = fetch_price_text_auto(parts[1])
                else:
                    reply_text = fetch_price_text_auto("BTC")

            # (3) พิมพ์สัญลักษณ์เหรียญตรง ๆ เช่น BTC, ETH, sol/usdt
            if not reply_text and re.fullmatch(r"[A-Za-z0-9:/\- ]{2,20}", user_text):
                reply_text = fetch_price_text_auto(user_text)

            # (4) วิเคราะห์สัญญาณ: analyze หรือ "<sym> <tf>"
            if not reply_text:
                args = _parse_text(user_text)
                symbol, tf, profile = args["symbol"], args["tf"], args["profile"]
                reply_text = build_line_text(symbol, tf, profile=profile)

            # ---- ส่งกลับ
            reply_token = ev.get("replyToken")
            if reply_token and reply_text:
                await _reply_text(reply_token, reply_text)

        except Exception as e:
            log.exception("LINE webhook event error: %s", e)

    return {"ok": True}

# =============================================================================
# LINE BOT API fallback (คงไว้กรณี import ที่อื่น)
# =============================================================================
try:
    from linebot import LineBotApi
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
except Exception:
    class _LineAPINoop:
        def push_message(self, *a, **k): pass
        def reply_message(self, *a, **k): pass
        def broadcast(self, *a, **k): pass
    line_bot_api = _LineAPINoop()
