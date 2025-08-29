# app/settings/alerts.py

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class AlertSettings:
    # สัญลักษณ์ยอดนิยม
    TOP10_SYMBOLS: List[str] = field(
        default_factory=lambda: [
            "BTCUSDT",
            "ETHUSDT",
            "BNBUSDT",
            "SOLUSDT",
            "XRPUSDT",
            "ADAUSDT",
            "DOGEUSDT",
            "TONUSDT",
            "TRXUSDT",
            "LINKUSDT",
        ]
    )
    # interval สำหรับเช็กแจ้งเตือน (นาที)
    PRICE_ALERT_INTERVAL_MIN: int = 5
    # เปิด/ปิด push notification (ชื่อหลัก)
    ENABLE_PUSH: bool = True

    # ✅ alias ใช้แทน .enabled ได้ (กัน error)
    @property
    def enabled(self) -> bool:
        return self.ENABLE_PUSH


# ✅ ตัวแปร global ที่ให้ import ได้
alert_settings = AlertSettings()
