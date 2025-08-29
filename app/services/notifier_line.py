# app/services/notifier_line.py
from __future__ import annotations
import os
import time
from typing import Optional, Tuple

__all__ = ["get_notifier", "LineNotifier"]

try:
    from app.adapters.delivery_line import push_text as line_push_text
except Exception:
    line_push_text = None  # ป้องกัน import error

# ========== De-dup ในหน่วยความจำ ==========
_last_text: Optional[str] = None
_last_ts: float = 0.0

def _dedup_allowed(text: str, window_sec: Optional[int] = None) -> Tuple[bool, str]:
    """กันข้อความซ้ำเป๊ะภายในช่วงเวลา (default 30s)"""
    global _last_text, _last_ts
    now = time.time()
    win = int(os.getenv("LINE_DEDUP_SEC", "30")) if window_sec is None else int(window_sec)
    if win <= 0:
        return True, "DEDUP_DISABLED"
    if _last_text is not None and text.strip() == _last_text.strip():
        if (now - _last_ts) < win:
            return False, f"DEDUP_SUPPRESSED (within {win}s)"
    return True, "DEDUP_OK"

def _dedup_mark(text: str) -> None:
    global _last_text, _last_ts
    _last_text = text
    _last_ts = time.time()

# ========== Notifier ==========
class LineNotifier:
    """
    Gateway สำหรับส่งข้อความไป LINE (ใช้ push → USER_ID เดียว)
    โหมดควบคุมด้วย ENV: LINE_MODE = OFF | DUMMY | REAL
    """
    def __init__(self, token: Optional[str]) -> None:
        self.token = (token or "").strip()
        self.mode = (os.getenv("LINE_MODE", "REAL") or "REAL").upper()  # OFF/DUMMY/REAL
        self.real = (self.mode == "REAL") and bool(self.token) and callable(line_push_text)

    def info(self) -> str:
        if self.mode == "OFF":
            return "LineNotifier: OFF (suppress all sends)"
        if self.real:
            return "LineNotifier: REAL (push via LINE API)"
        if self.mode == "DUMMY":
            return "LineNotifier: DUMMY (forced by LINE_MODE=DUMMY)"
        if not self.token:
            return "LineNotifier: DUMMY (missing LINE_CHANNEL_ACCESS_TOKEN)"
        if not callable(line_push_text):
            return "LineNotifier: DUMMY (delivery_line adapter not available)"
        return "LineNotifier: DUMMY (unknown reason)"

    def broadcast(self, message: str) -> Tuple[bool, str]:
        """
        ส่งข้อความแบบ PUSH (ไม่ใช้ broadcast แล้ว)
        คืนค่า: (ok, detail)
        """
        msg = (message or "").strip()
        if not msg:
            return False, "empty message"

        if self.mode == "OFF":
            return True, "SUPPRESSED (LINE_MODE=OFF)"

        allowed, reason = _dedup_allowed(msg)
        if not allowed:
            return True, reason

        try:
            if self.real and callable(line_push_text):
                to_id = (os.getenv("LINE_USER_ID", "") or "").strip()
                if not to_id:
                    return False, "missing LINE_USER_ID for PUSH"
                status, body = line_push_text(to_id, msg, self.token)  # type: ignore
                _dedup_mark(msg)
                ok = 200 <= int(status) < 300
                return ok, f"LINE status={status}"
            else:
                _dedup_mark(msg)
                return True, f"DUMMY push: {msg[:200]}..."
        except Exception as e:
            return False, f"LINE error: {e}"

# ========== Entry point ==========
def get_notifier() -> LineNotifier:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip() or None
    return LineNotifier(token)
