# app/adapters/delivery_line.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# คลาส LineDelivery — adapter สำหรับ LINE Messaging API
# - reply_text(reply_token, text): ตอบกลับข้อความที่ผู้ใช้ส่งมา
# - push_text(to, text): ส่งข้อความหา user/room/group
# - broadcast_text(text): กระจายข้อความไปยังทุกคน (ระวัง quota)
#
# ใช้ requests.post ตรง (ถ้าอยากเปลี่ยน lib → เปลี่ยนที่นี่ทีเดียว)
# =============================================================================

from __future__ import annotations
import requests
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

class LineDelivery:
    def __init__(self, channel_access_token: str, channel_secret: str):
        if not channel_access_token or not channel_secret:
            raise ValueError("LINE credentials missing (access token/secret).")
        self.access_token = channel_access_token
        self.secret = channel_secret
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    # -------------------------------------------------------------------------
    # LAYER B) REPLY
    # -------------------------------------------------------------------------
    def reply_text(self, reply_token: str, text: str) -> Dict[str, Any]:
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        }
        return self._post(LINE_REPLY_URL, payload)

    # -------------------------------------------------------------------------
    # LAYER C) PUSH
    # -------------------------------------------------------------------------
    def push_text(self, to: str, text: str) -> Dict[str, Any]:
        payload = {
            "to": to,
            "messages": [{"type": "text", "text": text}],
        }
        return self._post(LINE_PUSH_URL, payload)

    # -------------------------------------------------------------------------
    # LAYER D) BROADCAST
    # -------------------------------------------------------------------------
    def broadcast_text(self, text: str) -> Dict[str, Any]:
        payload = {
            "messages": [{"type": "text", "text": text}],
        }
        return self._post(LINE_BROADCAST_URL, payload)

    # -------------------------------------------------------------------------
    # LAYER E) INTERNAL POST
    # -------------------------------------------------------------------------
    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            r = requests.post(url, headers=self.headers, json=payload, timeout=10)
            if r.status_code != 200:
                log.error("LINE API error %s: %s", r.status_code, r.text)
                return {"ok": False, "status": r.status_code, "body": r.text}
            return {"ok": True, "status": r.status_code, "body": r.text}
        except Exception as e:
            log.exception("LINE API request failed: %s", e)
            return {"ok": False, "error": str(e)}
