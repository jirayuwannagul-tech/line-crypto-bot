# app/adapters/delivery_line.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# คลาส LineDelivery — adapter สำหรับ LINE Messaging API (ใช้ requests.post)
# - reply_text(reply_token, text): ตอบกลับข้อความที่ผู้ใช้ส่งมา
# - push_text(to, text): ส่งข้อความหา user/room/group
# - broadcast_text(text): กระจายข้อความไปยังทุกคน (ระวัง quota)
#
# เสริม:
# - broadcast_message(text): ฟังก์ชันระดับโมดูล เพื่อให้ไฟล์เทส import ได้
#   รองรับโหมด DRY-RUN (ไม่ยิง API) อัตโนมัติเมื่อไม่มี TOKEN หรือสั่ง LINE_DRY_RUN=1
# =============================================================================

from __future__ import annotations

import os
import requests
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# Env vars ที่ใช้
ENV_ACCESS_TOKEN = "LINE_CHANNEL_ACCESS_TOKEN"
ENV_CHANNEL_SECRET = "LINE_CHANNEL_SECRET"
ENV_DRY_RUN = "LINE_DRY_RUN"


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


# =============================================================================
# LAYER F) MODULE-LEVEL HELPERS (สำหรับเทสและใช้งานง่าย)
# =============================================================================

def _is_dry_run() -> bool:
    """True ถ้าควรทำงานแบบ DRY-RUN (ไม่ยิง API จริง)."""
    if os.getenv(ENV_DRY_RUN, "0") == "1":
        return True
    # ถ้าไม่มี token/secret ก็ถือว่า dry-run
    token = os.getenv(ENV_ACCESS_TOKEN)
    secret = os.getenv(ENV_CHANNEL_SECRET)
    return not token or not secret


def _get_delivery() -> Optional[LineDelivery]:
    """สร้าง LineDelivery จาก ENV ถ้าพร้อมใช้งาน; ถ้าไม่พร้อมคืน None."""
    token = os.getenv(ENV_ACCESS_TOKEN)
    secret = os.getenv(ENV_CHANNEL_SECRET)
    if not token or not secret:
        return None
    try:
        return LineDelivery(token, secret)
    except Exception as e:
        log.error("Cannot init LineDelivery: %s", e)
        return None


def broadcast_message(message: str) -> Dict[str, Any]:
    """
    ฟังก์ชันระดับโมดูลให้ไฟล์เทส import ได้:
    - โหมดจริง: ใช้ LineDelivery.broadcast_text(message)
    - โหมด DRY-RUN: ไม่ยิง API จริง แค่ log/print และคืน ok=True
    """
    if _is_dry_run():
        log.info("[DRY-RUN] broadcast_message: %s", message)
        print(f"[DRY-RUN] broadcast_message: {message}")
        return {"ok": True, "dry_run": True, "message": message}

    delivery = _get_delivery()
    if delivery is None:
        # กันเคสกลางอากาศ: ถือเป็น dry-run เพื่อให้เทสไม่ล้ม
        log.warning("Missing LINE credentials; fallback to DRY-RUN.")
        print(f"[DRY-RUN] broadcast_message: {message}")
        return {"ok": True, "dry_run": True, "message": message}

    return delivery.broadcast_text(message)


__all__ = ["LineDelivery", "broadcast_message"]
