"""
app/utils/state_store.py
------------------------
เลเยอร์: utils
หน้าที่: เก็บสถานะ (state) สำหรับระบบแจ้งเตือนแบบ in-memory
- baseline (ราคาตั้งต้น)
- last_alert_ts (เวลาที่แจ้งล่าสุด)
- last_state (สถานะปัจจุบัน: idle | armed)
ใช้ asyncio.Lock() กัน race เผื่อมีหลาย job
"""

import asyncio
import time
from typing import Dict, Any, Optional

# เก็บ state ทั้งหมดไว้ใน dict กลาง
# โครงสร้าง: {symbol: {"baseline": float, "last_alert_ts": float|None, "last_state": str}}
_state_store: Dict[str, Dict[str, Any]] = {}

# lock ป้องกัน race condition เวลาแก้ไข state
_state_lock = asyncio.Lock()


def get_state(symbol: str) -> Dict[str, Any]:
    """ดึง state ของ symbol ถ้าไม่มีจะสร้างใหม่"""
    return _state_store.setdefault(
        symbol,
        {"baseline": None, "last_alert_ts": None, "last_state": "idle"},
    )


def set_baseline(symbol: str, price: float) -> None:
    """ตั้ง baseline ของ symbol และ mark state เป็น 'armed'"""
    state = get_state(symbol)
    state["baseline"] = price
    state["last_state"] = "armed"
    state["last_alert_ts"] = None


def mark_alerted(symbol: str, now: Optional[float] = None) -> None:
    """อัปเดตเวลาที่ alert ล่าสุด"""
    state = get_state(symbol)
    state["last_alert_ts"] = now or time.time()
    state["last_state"] = "idle"


def should_alert(symbol: str, pct_change: float, threshold_pct: float, cooldown_sec: int) -> bool:
    """
    ตรวจสอบว่าควร alert หรือไม่
    - ถ้า abs(pct_change) >= threshold_pct และพ้นช่วง cooldown แล้ว -> True
    - ไม่งั้น -> False
    """
    state = get_state(symbol)
    last_alert = state.get("last_alert_ts")
    now = time.time()

    if abs(pct_change) >= threshold_pct:
        if not last_alert or (now - last_alert) >= cooldown_sec:
            return True
    return False


def reset_state(symbol: str) -> None:
    """รีเซ็ต state (ใช้สำหรับทดสอบ)"""
    _state_store[symbol] = {"baseline": None, "last_alert_ts": None, "last_state": "idle"}


# ===== 🧪 คำสั่งทดสอบ =====
# python3 -c "from app.utils.state_store import *; set_baseline('BTC', 60000.0); print(get_state('BTC'))"
# ✅ Acceptance: {'baseline': 60000.0, 'last_alert_ts': None, 'last_state': 'armed'}
