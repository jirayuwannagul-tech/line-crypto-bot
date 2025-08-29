# app/routers/config.py
from __future__ import annotations

from typing import Optional, Dict, Any
from fastapi import APIRouter
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

router = APIRouter(prefix="/config", tags=["config"])


class Settings(BaseSettings):
    """
    โหลดคอนฟิกจาก ENV/.env สำหรับระบบแจ้งเตือน/สครอน/LINE ฯลฯ
    - อนุญาต ENV ที่ไม่มีในโมเดล (extra='ignore') -> กันล้มตอนรันบนเครื่อง/คลาวด์
    - โหลดจากไฟล์ .env ถ้ามี
    - ไม่สนตัวพิมพ์เล็ก/ใหญ่
    """
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ====== LINE / Alert / Scheduler (เติมเท่าที่จำเป็น) ======
    line_channel_access_token: Optional[str] = Field(default=None, description="LINE channel access token")
    line_channel_secret: Optional[str] = Field(default=None, description="LINE channel secret")
    line_user_id: Optional[str] = Field(default=None, description="Default LINE user id to push")

    scheduler_token: Optional[str] = Field(default=None, description="Internal token for Cloud Scheduler to call /jobs")
    alert_enabled: bool = Field(default=True, description="Enable/disable LINE alert push")
    alert_threshold_pct: float = Field(default=0.03, description="Default alert threshold %")
    alert_cooldown_sec: int = Field(default=900, description="Cooldown seconds between alerts")
    alert_poll_sec: int = Field(default=10, description="Polling interval seconds")

    # ====== Data/Provider (ระบุเท่าที่ใช้) ======
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None

    # ====== Misc ======
    env_name: Optional[str] = Field(default=None, description="Environment name (local/staging/prod)")


settings = Settings()


def _mask(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if not isinstance(v, str):
        return str(v)
    if len(v) <= 6:
        return "***"
    return v[:3] + "***" + v[-3:]


@router.get("/health")
def config_health() -> Dict[str, Any]:
    return {"ok": True, "env": settings.env_name or "unknown"}


@router.get("/")
def config_summary() -> Dict[str, Any]:
    """
    สรุปคีย์หลักๆ แบบ mask (ไม่โชว์ค่าเต็ม/ความลับ)
    """
    return {
        "env": settings.env_name or "unknown",
        "alert": {
            "enabled": settings.alert_enabled,
            "threshold_pct": settings.alert_threshold_pct,
            "cooldown_sec": settings.alert_cooldown_sec,
            "poll_sec": settings.alert_poll_sec,
        },
        "line": {
            "channel_access_token": _mask(settings.line_channel_access_token),
            "channel_secret": _mask(settings.line_channel_secret),
            "user_id": _mask(settings.line_user_id),
        },
        "scheduler": {"token": _mask(settings.scheduler_token)},
        "providers": {
            "binance_api_key": _mask(settings.binance_api_key),
            "binance_api_secret": _mask(settings.binance_api_secret),
        },
    }
