# app/routers/line_webhook.py
# =============================================================================
# LINE Webhook Router
# -----------------------------------------------------------------------------
# - รับ Webhook จาก LINE Messaging API
# - รองรับ keyword reply, ราคา <symbol>, พิมพ์สัญลักษณ์เหรียญตรง ๆ (BTC/ETH/...)
# - เก็บ userId ล่าสุด และมีเอ็นด์พอยต์ /debug/push_news สำหรับทดสอบ push
# - background loop แจ้งข่าว mock ทุก NEWS_PUSH_EVERY_SEC วินาที (ค่า env)
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, Optional
import os
import re
import logging
import asyncio
import datetime as _dt

from fastapi import APIRouter, Request, HTTPException
import httpx

# ---- Internal layers
from app.engine.signal_engine import build_line_text          # วิเคราะห์สัญญาณ
from app.utils.crypto_price import fetch_price_text_auto      # ดึงราคาพร้อม auto-parse
from app.features.replies.keyword_reply import get_reply      # keyword layer

router = APIRouter()
log = logging.getLogger(__name__)

# เก็บ userId ล่าสุดไว้สำหรับ push ทดสอบ
_last_user_id: Optional[str] = None

# interval สำหรับ push ข่าว mock (วินาที)
_NEWS_INTERVAL = int(os.getenv("NEWS_PUSH_EVERY_SEC", "0"))
_news_task: Optional[asyncio.Task] = None

# =============================================================================
# LINE reply helper
# =============================================================================
async def _reply_text(reply_token: str, text: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
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
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
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
            if _last_user_id:
                now = _dt.datetime.now().strftime("%H:%M:%S")
                text = f"📰 ข่าวทดสอบ {now} — ระบบแจ้งเตือนทำงานจริง"
                await _push_text(_last_user_id, text)
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
# COMMAND PARSER (สำหรับ analyze)
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
        symbol = m1.group(1).upper()
        tf = m1.group(2).upper()
        return {"symbol": symbol, "tf": tf, "profile": profile}

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
                    reply_text = fetch_price_text_auto(parts[1])
                else:
                    reply_text = fetch_price_text_auto("BTC")

            # 2) พิมพ์สัญลักษณ์เหรียญตรง ๆ
            if not reply_text and re.fullmatch(r"[A-Za-z0-9:/\- ]{2,20}", user_text):
                reply_text = fetch_price_text_auto(user_text)

            # 3) keyword ปกติ
            if not reply_text:
                reply_text = get_reply(user_text)

            # 4) วิเคราะห์สัญญาณ
            if not reply_text:
                args = _parse_text(user_text)
                symbol, tf, profile = args["symbol"], args["tf"], args["profile"]
                reply_text = build_line_text(symbol, tf, profile=profile)

            # ส่งกลับ
            reply_token = ev.get("replyToken")
            if reply_token and reply_text:
                await _reply_text(reply_token, reply_text)

        except Exception as e:
            log.exception("LINE webhook event error: %s", e)

    return {"ok": True}

# =============================================================================
# DEBUG: push news
# =============================================================================
@router.post("/debug/push_news")
async def debug_push_news(request: Request) -> Dict[str, Any]:
    body = await request.json()
    text = (body or {}).get("text", "📰 ข่าวทดสอบ: ระบบ push พร้อมใช้งาน")
    if not _last_user_id:
        raise HTTPException(status_code=400, detail="ยังไม่พบ userId — กรุณาส่งข้อความหาบอทก่อน")
    await _push_text(_last_user_id, text)
    return {"ok": True, "pushed_to": _last_user_id}
