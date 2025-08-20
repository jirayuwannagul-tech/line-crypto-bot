# =============================================================================
# LINE Delivery Adapter - reply / push / broadcast
# =============================================================================

import os
import re
import httpx
import logging
from dotenv import load_dotenv
from pathlib import Path

# โหลด .env
load_dotenv(dotenv_path=Path(".") / ".env")

logger = logging.getLogger(__name__)

LINE_API_REPLY = "https://api.line.me/v2/bot/message/reply"
LINE_API_PUSH = "https://api.line.me/v2/bot/message/push"
LINE_API_BROADCAST = "https://api.line.me/v2/bot/message/broadcast"

# --- remove only invisible BOM/zero-width chars; don't mutate valid tokens ---
_INVISIBLES = ["\u200b", "\u200c", "\u200d", "\ufeff"]

def _clean_invisible(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    for ch in _INVISIBLES:
        s = s.replace(ch, "")
    return s

def _validate_token(tok: str) -> bool:
    # LINE token โดยปกติเป็น base64-like: ตัวอักษร/ตัวเลข + / = _ - .
    return re.fullmatch(r"[A-Za-z0-9+\-_/=\.~]+", tok) is not None

LINE_CHANNEL_ACCESS_TOKEN = _clean_invisible(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))

if LINE_CHANNEL_ACCESS_TOKEN and not _validate_token(LINE_CHANNEL_ACCESS_TOKEN):
    bad = [hex(ord(c)) for c in LINE_CHANNEL_ACCESS_TOKEN if not re.fullmatch(r"[A-Za-z0-9+\-_/=\.~]", c)]
    logger.error("LINE_CHANNEL_ACCESS_TOKEN has invalid chars: %s", bad)

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

async def push_message(user_id: str, text: str) -> None:
    headers = _auth_headers()
    if not headers:
        return
    payload = {"to": user_id, "messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_PUSH, headers=headers, json=payload)
        if resp.is_error:
            logger.error("push_message failed: %s %s", resp.status_code, resp.text)

async def broadcast_message(text: str) -> None:
    headers = _auth_headers()
    if not headers:
        return
    payload = {"messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_BROADCAST, headers=headers, json=payload)
        if resp.is_error:
            logger.error("broadcast_message failed: %s %s", resp.status_code, resp.text)
