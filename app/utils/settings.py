import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()
@dataclass(frozen=True)
class Settings:
    APP_NAME: str = "Line Crypto Bot"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    def validate_line(self) -> None:
        missing = []
        if not self.LINE_CHANNEL_SECRET: missing.append("LINE_CHANNEL_SECRET")
        if not self.LINE_CHANNEL_ACCESS_TOKEN: missing.append("LINE_CHANNEL_ACCESS_TOKEN")
        if missing: raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
settings = Settings()
