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

import logging
import os
from typing import Optional, Dict, Any

import requests

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


# -----------------------------------------------------------------------------
# Compatibility shim for tests
# -----------------------------------------------------------------------------
# ให้ test_* สามารถ import broadcast_message จากโมดูลนี้ได้โดยตรง
# ถ้าไม่มี ENV (LINE_CHANNEL_ACCESS_TOKEN/LINE_CHANNEL_SECRET)
# จะทำงานแบบ dry-run เพื่อไม่พึ่งพา network และลด flakiness ของเทสต์
# -----------------------------------------------------------------------------

def _get_credentials() -> tuple[Optional[str], Optional[str]]:
    return (
        os.getenv("LINE_CHANNEL_ACCESS_TOKEN"),
        os.getenv("LINE_CHANNEL_SECRET"),
    )


def broadcast_message(text: str) -> Dict[str, Any]:
    """
    Broadcast ข้อความแบบง่าย ๆ สำหรับใช้ในโปรดักชัน/เทสต์

    Returns:
      {
        "ok": bool,
        "mode": "live" | "dry-run",
        "message": str,
        "response": Any | None,   # ใน live mode จะเป็น dict จาก _post()
        # "error": str             # มีเมื่อ live mode ล้มเหลว
      }
    """
    token, secret = _get_credentials()
    if not token or not secret:
        # ไม่มี credentials → ไม่ยิง API จริง ให้เทสต์ import ผ่านและรันต่อได้
        return {"ok": True, "mode": "dry-run", "message": text, "response": None}

    try:
        delivery = LineDelivery(token, secret)
        res = delivery.broadcast_text(text)
        return {
            "ok": bool(res.get("ok")),
            "mode": "live",
            "message": text,
            "response": res,
        }
    except Exception as e:
        return {
            "ok": False,
            "mode": "live",
            "message": text,
            "response": None,
            "error": str(e),
        }
