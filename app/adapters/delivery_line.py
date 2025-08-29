# app/adapters/delivery_line.py
"""
LINE Delivery Adapter (requests)
- broadcast_text(message, token=None) -> Tuple[int, str]
- push_text(to, message, token=None) -> Tuple[int, str]
- LineDelivery(token, secret="").broadcast_text(...)/push_text(...)
"""
from __future__ import annotations

from typing import Dict, Any, Tuple, Optional
import os
import json
import requests

__all__ = ["broadcast_text", "push_text", "LineDelivery"]

LINE_API_BASE = "https://api.line.me"
LINE_API_BROADCAST = f"{LINE_API_BASE}/v2/bot/message/broadcast"
LINE_API_PUSH = f"{LINE_API_BASE}/v2/bot/message/push"

# ---------------- Token Cleaner ----------------
def _clean_visible_ascii(s: str) -> str:
    """
    ล้างอักขระที่ไม่ใช่ ASCII มองเห็น (32<ord<127) + strip
    กัน zero-width/CR/LF/smart quotes ที่ทำให้ Authorization 401
    """
    if not s:
        return ""
    return "".join(ch for ch in s if 32 < ord(ch) < 127).strip()

# ---------------- Low-level HTTP ----------------
def _post_json(url: str, body: Dict[str, Any], token: str, timeout: int = 10) -> Tuple[int, str]:
    tok = _clean_visible_ascii(token)
    headers = {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "line-crypto-bot/1.0",
    }
    try:
        # ส่งเป็น json= ก็ได้ แต่เข้ารหัสเองเพื่อควบคุมให้ชัด
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        resp = requests.post(url, data=payload, headers=headers, timeout=timeout)
        # คืน status + เนื้อข้อความ (จำกัดความยาวกัน log ล้น)
        text = resp.text[:2000] if resp.text else ""
        return resp.status_code, text
    except requests.RequestException as e:
        return 0, f"RequestsError: {e}"

# ---------------- High-level helpers ----------------
def broadcast_text(message: str, token: Optional[str] = None) -> Tuple[int, str]:
    """
    ส่งข้อความ broadcast ไปยังผู้ติดตามทั้งหมด
    คืนค่า: (status_code, response_text|error)
    """
    raw_tok = token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
    tok = _clean_visible_ascii(raw_tok)
    if not tok:
        raise ValueError("LINE_CHANNEL_ACCESS_TOKEN missing")

    text = (message or "").strip()
    if not text:
        return 400, "empty message"
    text = text[:5000]  # ข้อจำกัด LINE

    body = {"messages": [{"type": "text", "text": text}]}
    return _post_json(LINE_API_BROADCAST, body, tok)

def push_text(to: str, message: str, token: Optional[str] = None) -> Tuple[int, str]:
    """
    ส่งข้อความ push ไปยัง userId/roomId/groupId ที่ระบุ
    คืนค่า: (status_code, response_text|error)
    """
    raw_tok = token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
    tok = _clean_visible_ascii(raw_tok)
    if not tok:
        raise ValueError("LINE_CHANNEL_ACCESS_TOKEN missing")

    to_id = (to or os.getenv("LINE_USER_ID") or "").strip()
    if not to_id:
        return 400, "missing 'to' (userId/roomId/groupId) and LINE_USER_ID not set"

    text = (message or "").strip()
    if not text:
        return 400, "empty message"
    text = text[:5000]

    body = {
        "to": to_id,
        "messages": [{"type": "text", "text": text}],
    }
    return _post_json(LINE_API_PUSH, body, tok)

# ---------------- OO Wrapper ----------------
class LineDelivery:
    """
    ใช้แบบ OO:
        ld = LineDelivery(token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN",""))
        ld.broadcast_text("hello")
        ld.push_text("<USER_ID>", "hello")
    """
    def __init__(self, token: str, secret: str = "") -> None:
        self.token = _clean_visible_ascii(token or "")
        self.secret = secret  # เผื่อใช้ในอนาคต (ไม่บังคับ)
        if not self.token:
            # ไม่ raise เพื่อให้ใช้งานกับโหมด DUMMY ได้ในเลเยอร์บน
            pass

    def broadcast_text(self, message: str) -> Tuple[int, str]:
        return broadcast_text(message, token=self.token)

    def push_text(self, to: str, message: str) -> Tuple[int, str]:
        return push_text(to, message, token=self.token)
