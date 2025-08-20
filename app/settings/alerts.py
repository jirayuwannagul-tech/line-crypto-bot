"""
app/settings/alerts.py
----------------------
เลเยอร์: settings
หน้าที่: โหลดค่าการตั้งค่าเกี่ยวกับ Alert (แจ้งเตือนราคา) จาก environment variables
"""

# ===== Import ที่ถูกต้องสำหรับ Pydantic v2 =====
from pydantic_settings import BaseSettings, SettingsConfigDict  # ใช้ BaseSettings และ config ของ pydantic-settings
from pydantic import Field  # ใช้ Field สำหรับกำหนดค่า default + mapping env


class AlertSettings(BaseSettings):
    """คลาสสำหรับอ่านค่า ENV เกี่ยวกับ Alert"""

    enabled: bool = Field(default=True, env="ALERT_ENABLED")              # เปิด/ปิดระบบแจ้งเตือน
    symbol: str = Field(default="BTC", env="ALERT_SYMBOL")                # เหรียญที่จะติดตาม
    threshold_pct: float = Field(default=5.0, env="ALERT_THRESHOLD_PCT")  # % เปลี่ยนแปลงที่จะทริกเกอร์
    poll_sec: int = Field(default=60, env="ALERT_POLL_SEC")               # รอบการตรวจสอบราคา (วินาที)
    cooldown_sec: int = Field(default=1800, env="ALERT_COOLDOWN_SEC")     # เวลาคูลดาวน์ก่อนแจ้งซ้ำ (วินาที)
    hysteresis_pct: float = Field(default=1.0, env="ALERT_HYSTERESIS_PCT")# hysteresis กันสัญญาณสั่น

    # ===== Config เพื่อให้ไม่ error แม้มี ENV อื่น ๆ =====
    model_config = SettingsConfigDict(
        extra="ignore",          # ข้ามค่า env ที่ไม่รู้จัก (ไม่ error)
        env_file=".env",         # โหลดค่าจากไฟล์ .env
        case_sensitive=False     # ไม่สนใจตัวพิมพ์เล็ก/ใหญ่
    )


# instance ใช้งานจริง
alert_settings = AlertSettings()

# ===== 🧪 คำสั่งทดสอบ =====
# python3 -c "from app.settings.alerts import alert_settings; print(alert_settings.model_dump())"
# ✅ Acceptance: แสดง dict เช่น
# {'enabled': True, 'symbol': 'BTC', 'threshold_pct': 5.0, 'poll_sec': 60, 'cooldown_sec': 1800, 'hysteresis_pct': 1.0}
