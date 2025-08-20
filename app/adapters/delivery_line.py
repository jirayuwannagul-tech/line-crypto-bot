# app/adapters/delivery_line.py
# =============================================================================
# LINE Delivery Adapter - reply / push / broadcast
# =============================================================================

import os
import re
import httpx
import logging
from dotenv import load_dotenv
from pathlib import Path

# โหลดค่าจาก .env โดยระบุพาธตรง (กันเคส interactive/`python -c`)
load_dotenv(dotenv_path=Path(".") / ".env")

logger = logging.getLogger(__name__)

LINE_API_REPLY = "https://api.line.me/v2/bot/message/reply"
LINE_API_PUSH = "https://api.line.me/v2/bot/message/push"
LINE_API_BROADCAST = "https://api.line.me/v2/bot/message/broadcast"


# --- sanitize token: ตัดอักขระนอกเหนือ ASCII/อนุญาตทิ้ง (กัน zero-width, ช่องว่างแปลก ๆ) ---
def _sanitize_token(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    # เก็บเฉพาะตัวที่คาดว่าจะเจอใน token ของ LINE (อักษร, ตัวเลข, + / = - _ . ~)
    s_clean = re.sub(r"[^A-Za-z0-9\+\-_/=\.~]", "", s)
    if s_clean != s:
        logger.warning("LINE_CHANNEL_ACCESS_TOKEN contained invalid characters; sanitized.")
    return s_clean


LINE_CHANNEL_ACCESS_TOKEN = _sanitize_token(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))


def _auth_headers() -> dict:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN is not set")
        return {}
    return {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


async def reply_message(reply_token: str, text: str) -> None:
    headers = _auth_headers()
    if not headers:
        return
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_REPLY, headers=headers, json=payload)
        if resp.is_error:
            logger.error("reply_message failed: %s %s", resp.status_code, resp.text)
        else:
            logger.info("reply_message sent: %s", text)


async def push_message(user_id: str, text: str) -> None:
    headers = _auth_headers()
    if not headers:
        return
    payload = {"to": user_id, "messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_PUSH, headers=headers, json=payload)
        if resp.is_error:
            logger.error("push_message failed: %s %s", resp.status_code, resp.text)
        else:
            logger.info("push_message sent to %s: %s", user_id, text)


async def broadcast_message(text: str) -> None:
    headers = _auth_headers()
    if not headers:
        return
    payload = {"messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_BROADCAST, headers=headers, json=payload)
        if resp.is_error:
            logger.error("broadcast_message failed: %s %s", resp.status_code, resp.text)
        else:
            logger.info("broadcast_message sent: %s", text)
