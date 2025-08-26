# =============================================================================
# Settings - ใช้ dataclass + validate ENV
# =============================================================================

import os
from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path

# โหลดไฟล์ .env
load_dotenv(dotenv_path=Path(".") / ".env")

@dataclass(frozen=True)
class Settings:
    # App
    APP_NAME: str = os.getenv("APP_NAME", "Line Crypto Bot")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8080"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

    # LINE Bot
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

    def validate_line(self) -> None:
        """เช็กว่ามีการตั้งค่า LINE channel env ครบหรือยัง"""
        missing = []
        if not self.LINE_CHANNEL_SECRET:
            missing.append("LINE_CHANNEL_SECRET")
        if not self.LINE_CHANNEL_ACCESS_TOKEN:
            missing.append("LINE_CHANNEL_ACCESS_TOKEN")
        if missing:
            raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

# instance ที่จะใช้งาน
settings = Settings()
