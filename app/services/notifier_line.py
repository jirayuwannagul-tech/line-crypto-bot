"""
notifier_line.py
================
Service สำหรับส่งข้อความไปยัง LINE Messaging API
- แยก Layer: Config / Client / Service / Helper
- รองรับโหลดค่าจาก ENV (.env + os.environ)
"""

from __future__ import annotations
import os
from typing import Optional
from dotenv import load_dotenv
from linebot import LineBotApi
from linebot.models import TextSendMessage

# =============================================================================
# CONFIG LAYER
# =============================================================================
# โหลดค่า .env (ใช้เฉพาะ local dev)
load_dotenv()

LINE_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_DEFAULT_TO = (
    os.environ.get("LINE_DEFAULT_TO")
    or os.environ.get("LINE_TO_ID")
    or os.environ.get("LINE_USER_ID")  # เผื่อกรณีตั้งชื่อนี้
)

# =============================================================================
# CLIENT LAYER
# =============================================================================
class LineClient:
    """Client สำหรับ LINE Messaging API"""

    def __init__(self, access_token: Optional[str] = None):
        token = access_token or LINE_ACCESS_TOKEN
        if not token:
            raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not set")
        self._api = LineBotApi(token)

    def push_text(self, text: str, to: str) -> None:
        """ส่งข้อความไปยัง userId/groupId"""
        self._api.push_message(to, TextSendMessage(text=text))


# =============================================================================
# SERVICE LAYER
# =============================================================================
class LineNotifier:
    """Wrapper สำหรับส่งข้อความเข้า LINE"""

    def __init__(self, access_token: Optional[str] = None, default_to: Optional[str] = None):
        self._client = LineClient(access_token)
        self._default_to = default_to or LINE_DEFAULT_TO
        if not self._default_to:
            raise RuntimeError("LINE_DEFAULT_TO / LINE_TO_ID / LINE_USER_ID not set")

    def push_text(self, text: str, to: Optional[str] = None) -> str:
        """ส่งข้อความ (default ไปยัง userId/groupId ที่ config ไว้)"""
        to_id = to or self._default_to
        self._client.push_text(text, to_id)
        return to_id


# =============================================================================
# HELPER LAYER
# =============================================================================
_notifier: Optional[LineNotifier] = None

def get_notifier() -> LineNotifier:
    """คืน LineNotifier แบบ singleton"""
    global _notifier
    if _notifier is None:
        _notifier = LineNotifier()
    return _notifier

def send_message(text: str, to: Optional[str] = None) -> str:
    """ฟังก์ชัน helper สำหรับส่งข้อความแบบเร็ว"""
    notifier = get_notifier()
    return notifier.push_text(text, to)


# =============================================================================
# DEBUG / TEST
# =============================================================================
if __name__ == "__main__":
    msg = "🚀 LINE notifier test message"
    try:
        to_id = send_message(msg)
        print(f"✅ sent test message to {to_id}")
    except Exception as e:
        print(f"❌ error: {e}")
