from __future__ import annotations
import os
from typing import Optional, Tuple

try:
    # ใช้ตัวส่งจริงที่เพิ่งเพิ่มไว้
    from app.adapters.delivery_line import broadcast_text as line_broadcast_text
except Exception:
    line_broadcast_text = None  # ป้องกัน import error

__all__ = ["get_notifier", "LineNotifier"]


class LineNotifier:
    """
    Wrapper ส่งข้อความไป LINE แบบ broadcast
    - ถ้าไม่มี TOKEN หรือ adapter ใช้ไม่ได้ -> ใช้ Dummy (log อย่างเดียว)
    - ถ้ามีครบ -> เรียก LINE API จริง
    """
    def __init__(self, token: Optional[str]):
        self.token = token
        self.real = bool(self.token) and callable(line_broadcast_text)

    def info(self) -> str:
        if self.real:
            return "LineNotifier: REAL (broadcast via LINE API)"
        if not self.token:
            return "LineNotifier: DUMMY (missing LINE_CHANNEL_ACCESS_TOKEN)"
        if not callable(line_broadcast_text):
            return "LineNotifier: DUMMY (delivery_line adapter not available)"
        return "LineNotifier: DUMMY (unknown reason)"

    def broadcast(self, message: str) -> Tuple[bool, str]:
        """
        คืนค่า (ok, detail)
        """
        if not message or not message.strip():
            return False, "empty message"
        if self.real:
            try:
                status, body = line_broadcast_text(message, self.token)  # type: ignore
                ok = 200 <= status < 300
                return ok, f"LINE status={status}"
            except Exception as e:
                return False, f"LINE error: {e}"
        # Dummy: log/echo แทน
        return True, f"DUMMY broadcast: {message[:200]}..."

def get_notifier() -> LineNotifier:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip() or None
    return LineNotifier(token)
