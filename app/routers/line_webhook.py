# app/routers/line_webhook.py
# =============================================================================
# LAYER A) OVERVIEW (FastAPI Router for LINE Webhook)
# -----------------------------------------------------------------------------
# หน้าที่:
# - รับ Webhook จาก LINE Messaging API
# - แยกข้อความผู้ใช้ → สั่งวิเคราะห์ผ่าน service → ตอบกลับ
# - รองรับคำสั่งโปรไฟล์ เช่น: "analyze BTCUSDT 1D profile:chinchot"
#   ค่าดีฟอลต์: symbol=BTCUSDT, tf=1D, profile=baseline
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, Optional
import os
import re
import logging

from fastapi import APIRouter, Request, HTTPException

from app.services.signal_service import analyze_and_get_text
from app.adapters.delivery_line import LineDelivery

router = APIRouter()
log = logging.getLogger(__name__)

# =============================================================================
# LAYER B) ENV & CLIENT
# -----------------------------------------------------------------------------
# - ใช้ access token/secret จาก ENV (ถ้าไม่มี ให้ raise 400 ตอน runtime เพื่อชัดเจน)
# - คลาส LineDelivery เป็นตัวห่อ (adapter) สำหรับ reply/push
# =============================================================================

def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v if v not in (None, "") else default

CHANNEL_ACCESS_TOKEN = _get_env("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = _get_env("LINE_CHANNEL_SECRET")

# สร้าง client หนึ่งตัวใช้ร่วมกัน
_line_client: Optional[LineDelivery] = None
def _client() -> LineDelivery:
    global _line_client
    if _line_client is None:
        if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
            raise HTTPException(status_code=400, detail="LINE credentials missing in ENV.")
        _line_client = LineDelivery(CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET)
    return _line_client

# =============================================================================
# LAYER C) COMMAND PARSER
# -----------------------------------------------------------------------------
# รองรับรูปแบบ:
#   "analyze BTCUSDT 1D profile:chinchot"
#   "analyze ethusdt 4h"
#   "btc 1d"
#   ไม่มีคำสั่ง → ใช้ค่า default
# =============================================================================

_SYM_RE = r"[A-Z0-9:\-/]{3,20}"

def _parse_text(text: str) -> Dict[str, str]:
    t = (text or "").strip()
    t_upper = t.upper()

    # defaults
    symbol = "BTCUSDT"
    tf = "1D"
    profile = "baseline"

    # profile:<name>
    m_prof = re.search(r"profile:([a-zA-Z0-9_\-]+)", t, flags=re.IGNORECASE)
    if m_prof:
        profile = m_prof.group(1).strip()

    # pattern 1: "analyze SYMBOL TF ..."
    m1 = re.search(rf"\banalyze\s+({_SYM_RE})\s+([0-9]+[HDW])\b", t_upper)
    if m1:
        symbol = m1.group(1).replace(":", "").replace("/", "")
        tf = m1.group(2).upper()
        return {"symbol": symbol, "tf": tf, "profile": profile}

    # pattern 2: "SYMBOL TF"
    m2 = re.search(rf"\b({_SYM_RE})\s+([0-9]+[HDW])\b", t_upper)
    if m2:
        symbol = m2.group(1).replace(":", "").replace("/", "")
        tf = m2.group(2).upper()
        return {"symbol": symbol, "tf": tf, "profile": profile}

    # fallbacks
    return {"symbol": symbol, "tf": tf, "profile": profile}

# =============================================================================
# LAYER D) WEBHOOK HANDLER
# -----------------------------------------------------------------------------
# LINE จะเรียก POST /line/webhook ด้วย body ตาม spec (events[])
# เราอ่าน text จาก message event → วิเคราะห์ → reply token
# =============================================================================

@router.post("/line/webhook")
async def line_webhook(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = (body or {}).get("events", [])
    if not events:
        # เงียบ ๆ แต่ตอบ 200 ให้ LINE ไม่รีไทร
        return {"ok": True}

    for ev in events:
        try:
            ev_type = ev.get("type")
            if ev_type != "message":
                continue

            msg = ev.get("message", {})
            if msg.get("type") != "text":
                continue

            user_text = msg.get("text", "")
            args = _parse_text(user_text)
            symbol = args["symbol"]
            tf = args["tf"]
            profile = args["profile"]

            # วิเคราะห์แล้วสร้างข้อความสำหรับตอบ
            reply_text = analyze_and_get_text(symbol, tf, profile=profile)

            # ส่งกลับผ่าน replyToken
            reply_token = ev.get("replyToken")
            if reply_token:
                _client().reply_text(reply_token, reply_text)
        except Exception as e:
            log.exception("LINE webhook event error: %s", e)

    return {"ok": True}
