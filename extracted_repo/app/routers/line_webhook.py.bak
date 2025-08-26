# app/routers/line_webhook.py
# =============================================================================
# LINE Webhook Router
# -----------------------------------------------------------------------------
# - รับ Webhook จาก LINE Messaging API
# - รองรับ keyword reply, ราคา BTC, analyze
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, Optional
import os
import re
import logging

from fastapi import APIRouter, Request, HTTPException

from app.engine.signal_engine import build_line_text
from app.adapters.delivery_line import LineDelivery
from app.utils.crypto_price import fetch_price_text
from app.features.replies.keyword_reply import get_reply  # ✅ ใช้ keyword layer

router = APIRouter()
log = logging.getLogger(__name__)

# =============================================================================
# ENV & CLIENT
# =============================================================================
def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v if v not in (None, "") else default

CHANNEL_ACCESS_TOKEN = _get_env("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = _get_env("LINE_CHANNEL_SECRET")

_line_client: Optional[LineDelivery] = None
def _client() -> LineDelivery:
    global _line_client
    if _line_client is None:
        if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
            raise HTTPException(status_code=400, detail="LINE credentials missing in ENV.")
        _line_client = LineDelivery(CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET)
    return _line_client

# =============================================================================
# COMMAND PARSER
# =============================================================================
_SYM_RE = r"[A-Z0-9:\-/]{3,20}"

def _parse_text(text: str) -> Dict[str, str]:
    t = (text or "").strip()
    t_upper = t.upper()

    symbol = "BTCUSDT"
    tf = "1D"
    profile = "baseline"

    m_prof = re.search(r"profile:([a-zA-Z0-9_\-]+)", t, flags=re.IGNORECASE)
    if m_prof:
        profile = m_prof.group(1).strip()

    m1 = re.search(rf"\banalyze\s+({_SYM_RE})\s+([0-9]+[HDW])\b", t_upper)
    if m1:
        symbol = m1.group(1).replace(":", "").replace("/", "")
        tf = m1.group(2).upper()
        return {"symbol": symbol, "tf": tf, "profile": profile}

    m2 = re.search(rf"\b({_SYM_RE})\s+([0-9]+[HDW])\b", t_upper)
    if m2:
        symbol = m2.group(1).replace(":", "").replace("/", "")
        tf = m2.group(2).upper()
        return {"symbol": symbol, "tf": tf, "profile": profile}

    return {"symbol": symbol, "tf": tf, "profile": profile}

# =============================================================================
# WEBHOOK HANDLER
# =============================================================================
@router.post("/webhook")   # ✅ ใช้ /webhook (prefix="/line" จะทำให้เป็น /line/webhook)
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

            user_text = msg.get("text", "").strip()
            reply_text = None

            # (1) keyword replies เช่น สวัสดี, mock, btc
            reply_text = get_reply(user_text)

            # (2) ราคา BTC
            if not reply_text and user_text.lower().startswith("ราคา"):
                parts = user_text.split()
                if len(parts) >= 2:
                    sym = parts[1].upper()
                    if not sym.endswith("USDT"):
                        sym = sym + "USDT"
                else:
                    sym = "BTCUSDT"
                reply_text = fetch_price_text(sym)

            # (3) วิเคราะห์สัญญาณ
            if not reply_text:
                args = _parse_text(user_text)
                symbol, tf, profile = args["symbol"], args["tf"], args["profile"]
                reply_text = build_line_text(symbol, tf, profile=profile)

            reply_token = ev.get("replyToken")
            if reply_token and reply_text:
                _client().reply_text(reply_token, reply_text)

        except Exception as e:
            log.exception("LINE webhook event error: %s", e)

    return {"ok": True}
