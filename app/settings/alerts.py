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

    # เกณฑ์เปอร์เซ็นต์เปลี่ยนแปลงเพื่อทริกเกอร์แจ้งเตือน (เชิงสัมบูรณ์) — 0.03 = 3%
    THRESHOLD_PCT: float = 0.03

    # ฮิสเทอรีซิสกันเด้งซ้ำเร็ว ๆ — 0.005 = 0.5%
    HYSTERESIS_PCT: float = 0.005

    # คูลดาวน์ระหว่างการแจ้งเตือนของสัญลักษณ์เดียวกัน (วินาที)
    COOLDOWN_SEC: int = 600

    # ✅ alias ใช้แทน .enabled ได้ (กันโค้ดเก่า)
    @property
    def enabled(self) -> bool:
        return self.ENABLE_PUSH

    # ✅ aliases สำหรับโค้ดที่อ้างชื่อเล็ก
    @property
    def threshold_pct(self) -> float:
        return self.THRESHOLD_PCT

    @property
    def hysteresis_pct(self) -> float:
        return self.HYSTERESIS_PCT

    @property
    def cooldown_sec(self) -> int:
        return self.COOLDOWN_SEC


# ✅ ตัวแปร global ที่ให้ import ได้
alert_settings = AlertSettings()
