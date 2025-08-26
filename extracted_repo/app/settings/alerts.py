# =============================================================================
# Alert Settings
# โหลดค่าการตั้งค่าเกี่ยวกับ Alert (แจ้งเตือนราคา) จาก environment variables
# =============================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AlertSettings(BaseSettings):
    """คลาสสำหรับอ่านค่า ENV เกี่ยวกับ Alert"""

    enabled: bool = Field(
        default=True,
        json_schema_extra={"env": "ALERT_ENABLED"},
    )  # เปิด/ปิดระบบแจ้งเตือน

    symbol: str = Field(
        default="BTC",
        json_schema_extra={"env": "ALERT_SYMBOL"},
    )  # เหรียญ default

    threshold_pct: float = Field(
        default=5.0,
        json_schema_extra={"env": "ALERT_THRESHOLD_PCT"},
    )  # % เปลี่ยนแปลงที่จะทริกเกอร์

    poll_sec: int = Field(
        default=60,
        json_schema_extra={"env": "ALERT_POLL_SEC"},
    )  # รอบตรวจสอบ (วินาที)

    cooldown_sec: int = Field(
        default=1800,
        json_schema_extra={"env": "ALERT_COOLDOWN_SEC"},
    )  # คูลดาวน์ (วินาที)

    hysteresis_pct: float = Field(
        default=1.0,
        json_schema_extra={"env": "ALERT_HYSTERESIS_PCT"},
    )  # กันสัญญาณสั่น

    model_config = SettingsConfigDict(
        extra="ignore",        # ข้าม env ที่ไม่รู้จัก
        env_file=".env",       # โหลดค่าจากไฟล์ .env
        case_sensitive=False   # ไม่สนใจตัวพิมพ์เล็ก/ใหญ่
    )


# instance ใช้งานจริง
alert_settings = AlertSettings()

# ===== 🧪 Test Command =====
# python3 -c "from app.settings.alerts import alert_settings; print(alert_settings.model_dump())"
