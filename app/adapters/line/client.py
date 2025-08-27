# [ไฟล์] app/adapters/line/client.py  (แทนที่ทั้งไฟล์)

from __future__ import annotations
import os
import json
import logging
from typing import Optional, Dict, Any
import httpx

# --- โหลด .env อัตโนมัติ ตั้งแต่ import โมดูลนี้ ---
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    _env_path = find_dotenv(usecwd=True) or ".env"
    load_dotenv(_env_path)
except Exception:
    # ถ้าไม่มี python-dotenv ก็ข้ามไป (สมมุติว่า ENV ถูก export ไว้แล้ว)
    pass

logger = logging.getLogger(__name__)

LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_API_REPLY = f"{LINE_API_BASE}/message/reply"
LINE_API_PUSH  = f"{LINE_API_BASE}/message/push"
LINE_API_BROADCAST = f"{LINE_API_BASE}/message/broadcast"

# อักขระมองไม่เห็น (BOM/zero-width) ที่ควรถูกลบทิ้ง
_INVISIBLES = ("\u200b", "\u200c", "\u200d", "\ufeff")

def _clean_invisible(raw: Optional[str]) -> str:
    if not raw:
        return ""
    s = raw.strip()
    for ch in _INVISIBLES:
        if ch in s:
            s = s.replace(ch, "")
    return s

def _get_token() -> Optional[str]:
    return _clean_invisible(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))

def _get_default_to() -> Optional[str]:
    # รองรับ userId/roomId/groupId; สำหรับทดสอบเดี่ยวให้ตั้ง LINE_USER_ID
    return _clean_invisible(os.getenv("LINE_USER_ID"))

def _headers(token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

def _post(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> httpx.Response:
    with httpx.Client(timeout=15.0) as cli:
        return cli.post(url, headers=headers, content=json.dumps(body, ensure_ascii=False))

def push_text(text: str, *, to: Optional[str] = None) -> Dict[str, Any]:
    """
    ส่งข้อความแบบ push ไปยัง LINE
    ต้องมี ENV: LINE_CHANNEL_ACCESS_TOKEN และ (LINE_USER_ID หรือระบุ to)
    คืนค่า: {"ok": bool, "status": int, "error": Optional[str]}
    """
    token = _get_token()
    target = _clean_invisible(to) or _get_default_to()
    if not token or not target:
        return {"ok": False, "status": 0, "error": "missing LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID"}

    msg = _clean_invisible(text) or "(empty)"
    headers = _headers(token)
    body = {"to": target, "messages": [{"type": "text", "text": msg}]}

    try:
        r = _post(LINE_API_PUSH, headers, body)
        if 200 <= r.status_code < 300:
            return {"ok": True, "status": r.status_code, "error": None}
        logger.warning("LINE push error %s: %s", r.status_code, r.text)
        return {"ok": False, "status": r.status_code, "error": r.text}
    except Exception as e:
        logger.exception("LINE push exception: %s", e)
        return {"ok": False, "status": 0, "error": str(e)}

def push_checkmark(text: str, *, to: Optional[str] = None) -> Dict[str, Any]:
    """แจ้ง TP พร้อมติ๊กถูก"""
    return push_text(f"✅ {text}", to=to)

def push_stop(text: str, *, to: Optional[str] = None) -> Dict[str, Any]:
    """แจ้งโดน SL"""
    return push_text(f"⛔ {text}", to=to)
