# app/routers/line_webhook.py
from __future__ import annotations

import os
import json
import hmac
import base64
import hashlib
import logging
from typing import Any, Dict, Set

import httpx
from fastapi import APIRouter, Request, Header, Response

router = APIRouter(tags=["line"])

# ตั้งค่าจาก ENV (อย่าลืมใส่ใน Render/เครื่องคุณ)
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

logger = logging.getLogger(__name__)


def _verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """ตรวจสอบ X-Line-Signature ตามคู่มือ LINE"""
    try:
        mac = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("utf-8")
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, convert_underscores=False),
) -> Response:
    """
    รับ LINE Webhook → log event ทั้งก้อน
    ดึง userId/groupId/roomId ออกมา และ (ออปชัน) reply echo กลับ
    """
    raw: bytes = await request.body()

    # 1) log ก้อนดิบสวย ๆ
    try:
        payload: Dict[str, Any] = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.error("LINE webhook: invalid JSON body")
        return Response(status_code=400)

    logger.info("LINE Webhook event (raw): %s", json.dumps(payload, ensure_ascii=False))

    # 2) ตรวจลายเซ็น (ถ้าตั้ง CHANNEL_SECRET)
    if CHANNEL_SECRET:
        if not x_line_signature:
            logger.warning("LINE webhook: missing X-Line-Signature header")
        else:
            ok = _verify_signature(CHANNEL_SECRET, raw, x_line_signature)
            if not ok:
                logger.warning("LINE webhook: signature verification FAILED")
            else:
                logger.info("LINE webhook: signature verification OK")

    # 3) ดึง IDs เพื่อเอาไปใช้ push
    user_ids: Set[str] = set()
    group_ids: Set[str] = set()
    room_ids: Set[str] = set()

    for ev in payload.get("events", []):
        src = ev.get("source", {})
        uid = src.get("userId")
        gid = src.get("groupId")
        rid = src.get("roomId")
        if uid:
            user_ids.add(uid)
        if gid:
            group_ids.add(gid)
        if rid:
            room_ids.add(rid)

    logger.info("Extracted IDs → users=%s groups=%s rooms=%s",
                list(user_ids), list(group_ids), list(room_ids))

    # 4) (ออปชัน) echo ข้อความกลับ เพื่อทดสอบ reply API
    for ev in payload.get("events", []):
        try:
            if ev.get("type") == "message" and "replyToken" in ev:
                text = ev.get("message", {}).get("text", "")
                await _reply_text(ev["replyToken"], f"รับแล้ว: {text or 'OK'}")
        except Exception as e:
            logger.warning("Reply failed (non-blocking): %s", e)

    # ต้องตอบ 200 เสมอให้ LINE
    return Response(status_code=200)


async def _reply_text(reply_token: str, text: str) -> None:
    """เรียก LINE reply API (ต้องตั้ง LINE_CHANNEL_ACCESS_TOKEN ให้ถูก)"""
    if not CHANNEL_ACCESS_TOKEN:
        # ไม่บล็อค flow แต่เตือนให้ไปตั้ง env
        logging.warning("CHANNEL_ACCESS_TOKEN not set; skip reply.")
        return

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code != 200:
            logging.warning("Reply API failed %s: %s", r.status_code, r.text)
        else:
            logging.info("Reply OK")
