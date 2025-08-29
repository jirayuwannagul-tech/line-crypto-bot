# app/routers/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ✅ ตั้งค่าพื้นฐาน
    APP_NAME: str = "Line Crypto Bot"
    VERSION: str = "0.1.0"
    DEBUG: bool = True

    # ✅ ตัวอย่างค่าที่มักใช้
    LINE_CHANNEL_SECRET: str = "your-line-channel-secret"
    LINE_CHANNEL_ACCESS_TOKEN: str = "your-line-access-token"

    # ✅ Database (ถ้าใช้ SQLite)
    DATABASE_URL: str = "sqlite:///./app/data/database.db"

    class Config:
        env_file = ".env"   # โหลดค่าจากไฟล์ .env ถ้ามี

# ✅ instance ใช้งาน
settings = Settings()
