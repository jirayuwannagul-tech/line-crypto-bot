import os
import re
import logging
import httpx

logger = logging.getLogger(__name__)

LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_API_REPLY = f"{LINE_API_BASE}/message/reply"
LINE_API_PUSH = f"{LINE_API_BASE}/message/push"
LINE_API_BROADCAST = f"{LINE_API_BASE}/message/broadcast"

# --- remove only invisible BOM/zero-width chars; don't mutate valid tokens ---
_INVISIBLES = ["\u200b", "\u200c", "\u200d", "\ufeff"]

def _clean_invisible(raw: str | None) -> str:
    if not raw:
        return ""
    s = raw.strip()
    for ch in _INVISIBLES:
        s = s.replace(ch, "")
    return s

def _validate_token(tok: str) -> bool:
    # LINE access token is base64-like
    return bool(re.fullmatch(r"[A-Za-z0-9+\-_/=\.~]+", tok))

LINE_CHANNEL_ACCESS_TOKEN = _clean_invisible(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))

if not LINE_CHANNEL_ACCESS_TOKEN:
    logger.error("LINE_CHANNEL_ACCESS_TOKEN is missing (ENV not set)")
elif not _validate_token(LINE_CHANNEL_ACCESS_TOKEN):
    bad = [hex(ord(c)) for c in LINE_CHANNEL_ACCESS_TOKEN if not re.fullmatch(r"[A-Za-z0-9+\-_/=\.~]", c)]
    logger.error("LINE_CHANNEL_ACCESS_TOKEN contains invalid chars: %s", bad)

def _auth_headers() -> dict:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not set")
    return {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

async def _post(url: str, payload: dict) -> dict:
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code == 401:
        raise RuntimeError(f"LINE 401 Authentication failed. Resp={resp.text}")
    if resp.is_error:
        raise RuntimeError(f"LINE API error {resp.status_code}: {resp.text}")
    return resp.json() if resp.text else {}

async def reply_message(reply_token: str, messages: list[dict]) -> None:
    payload = {"replyToken": reply_token, "messages": messages}
    await _post(LINE_API_REPLY, payload)

async def push_message(user_id: str, messages: list[dict]) -> None:
    payload = {"to": user_id, "messages": messages}
    await _post(LINE_API_PUSH, payload)

async def broadcast_message(messages: list[dict]) -> None:
    payload = {"messages": messages}
    await _post(LINE_API_BROADCAST, payload)
