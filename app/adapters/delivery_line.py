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
# - reply_message, push_message, broadcast_message: ฟังก์ชันระดับโมดูล
#   เพื่อให้ไฟล์อื่น/ไฟล์เทส import ใช้ได้สะดวก
# - รองรับโหมด DRY-RUN (ไม่ยิง API) อัตโนมัติเมื่อไม่มี TOKEN/SECRET
#   หรือกำหนด LINE_DRY_RUN=1
# - TIMEOUT ปรับได้ผ่าน ENV: LINE_TIMEOUT_SEC (ดีฟอลต์ 10 วินาที)
# =============================================================================

from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any

import requests

log = logging.getLogger(__name__)

# ==============================
# LINE API endpoints
# ==============================
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# ==============================
# ENV variable names
# ==============================
ENV_ACCESS_TOKEN = "LINE_CHANNEL_ACCESS_TOKEN"
ENV_CHANNEL_SECRET = "LINE_CHANNEL_SECRET"
ENV_DRY_RUN = "LINE_DRY_RUN"
ENV_DEFAULT_TO = "LINE_USER_ID"
ENV_TIMEOUT_SEC = "LINE_TIMEOUT_SEC"


def _env_timeout() -> float:
    """อ่าน timeout (วินาที) จาก ENV; ดีฟอลต์ 10"""
    try:
        return float(os.getenv(ENV_TIMEOUT_SEC, "10"))
    except Exception:
        return 10.0


def _is_dry_run() -> bool:
    """True ถ้าควรทำงานแบบ DRY-RUN (ไม่ยิง API จริง)."""
    if os.getenv(ENV_DRY_RUN, "0") == "1":
        return True
    # ถ้าไม่มี token/secret ก็ถือว่า dry-run
    token = os.getenv(ENV_ACCESS_TOKEN)
    secret = os.getenv(ENV_CHANNEL_SECRET)
    return not token or not secret


class LineDelivery:
    """
    Adapter หลักสำหรับเรียก LINE Messaging API

    Parameters
    ----------
    channel_access_token : str
        LINE channel access token
    channel_secret : str
        LINE channel secret (เก็บไว้เพื่ออ้างอิง/ตรวจสอบในระบบอื่น ๆ)
    dry_run : bool
        บังคับให้ทำงานแบบ DRY-RUN (ถ้าไม่ส่งมา จะตรวจจาก ENV ให้เอง)
    timeout_sec : float
        timeout ของ request (วินาที)
    """

    def __init__(
        self,
        channel_access_token: Optional[str],
        channel_secret: Optional[str],
        dry_run: Optional[bool] = None,
        timeout_sec: Optional[float] = None,
    ):
        self.access_token = (channel_access_token or "").strip()
        self.secret = (channel_secret or "").strip()
        # DRY-RUN: ถ้าไม่ได้กำหนดมา จะดูจาก ENV/credential ที่มี
        self.dry_run = _is_dry_run() if dry_run is None else bool(dry_run)
        self.timeout_sec = _env_timeout() if timeout_sec is None else float(timeout_sec)

        if not self.dry_run and (not self.access_token or not self.secret):
            # ถ้าจะยิงจริงแต่ไม่มี credential ให้ fail ไว ๆ
            raise ValueError("LINE credentials missing (access token/secret).")

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}" if self.access_token else "",
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
        if self.dry_run:
            log.info("[DRY-RUN] POST %s payload=%s", url, payload)
            print(f"[DRY-RUN] POST {url} payload={payload}")
            return {"ok": True, "dry_run": True, "status": 0, "body": ""}

        try:
            r = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout_sec,
            )
            # LINE API ปกติจะคืน 200 เมื่อสำเร็จ
            if r.status_code != 200:
                log.error("LINE API error %s: %s", r.status_code, r.text)
                return {"ok": False, "status": r.status_code, "body": r.text}
            return {"ok": True, "status": r.status_code, "body": r.text}
        except requests.Timeout as e:
            log.exception("LINE API request timeout: %s", e)
            return {"ok": False, "error": "timeout", "detail": str(e)}
        except Exception as e:
            log.exception("LINE API request failed: %s", e)
            return {"ok": False, "error": "exception", "detail": str(e)}


# =============================================================================
# LAYER F) MODULE-LEVEL HELPERS (สำหรับเทส/ใช้งานง่าย + backward-compat)
# =============================================================================

def _get_delivery() -> LineDelivery:
    """
    สร้าง LineDelivery จาก ENV เสมอ
    - ถ้ามี token/secret ครบ → โหมดจริง (dry_run=False)
    - ถ้าขาด → DRY-RUN
    """
    token = os.getenv(ENV_ACCESS_TOKEN)
    secret = os.getenv(ENV_CHANNEL_SECRET)
    dry_run = _is_dry_run()
    try:
        return LineDelivery(token, secret, dry_run=dry_run)
    except Exception as e:
        # กันเคส config เพี้ยน: fallback เป็น DRY-RUN เสมอ
        log.warning("Cannot init LineDelivery (%s). Fallback to DRY-RUN.", e)
        return LineDelivery("", "", dry_run=True)


# ===== ระดับโมดูล: API แบบใหม่ (ชื่ออ่านง่าย) =====
def reply_message(reply_token: str, message: str) -> Dict[str, Any]:
    delivery = _get_delivery()
    return delivery.reply_text(reply_token, message)


def push_message(message: str, to: Optional[str] = None) -> Dict[str, Any]:
    delivery = _get_delivery()
    dest = to or os.getenv(ENV_DEFAULT_TO)
    if not dest:
        log.info("[DRY-RUN] push_message (no recipient): %s", message)
        print(f"[DRY-RUN] push_message (no recipient): {message}")
        return {"ok": True, "dry_run": True, "status": 0, "body": "", "message": message}
    return delivery.push_text(dest, message)


def broadcast_message(message: str) -> Dict[str, Any]:
    delivery = _get_delivery()
    return delivery.broadcast_text(message)


# ===== ระดับโมดูล: BACKWARD-COMPAT (ชื่อเดิมที่โค้ดอื่นคาดหวัง) =====
def push_text(to: str, text: str) -> Dict[str, Any]:
    """คงชื่อเดิมไว้สำหรับโค้ดเก่า"""
    delivery = _get_delivery()
    return delivery.push_text(to, text)


def broadcast_text(text: str) -> Dict[str, Any]:
    """คงชื่อเดิมไว้สำหรับโค้ดเก่า"""
    delivery = _get_delivery()
    return delivery.broadcast_text(text)


__all__ = [
    # Class
    "LineDelivery",
    # Newer helper names
    "reply_message",
    "push_message",
    "broadcast_message",
    # Backward-compatible names
    "push_text",
    "broadcast_text",
]
