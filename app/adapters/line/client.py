import base64, hashlib, hmac, logging
from typing import Any
import httpx
from app.utils.settings import settings
logger = logging.getLogger(__name__)
LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"
def verify_signature(channel_secret: str, body_bytes: bytes, x_line_signature: str) -> bool:
    mac = hmac.new(channel_secret.encode("utf-8"), body_bytes, hashlib.sha256).digest()
    calc = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(calc, x_line_signature)
async def reply_message(reply_token: str, messages: list[dict[str, Any]]) -> None:
    headers = {"Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"replyToken": reply_token, "messages": messages}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(LINE_REPLY_ENDPOINT, headers=headers, json=payload)
        if r.status_code >= 300:
            logger.error("LINE reply error %s: %s", r.status_code, r.text)
            raise RuntimeError(f"LINE reply failed: {r.status_code}")
