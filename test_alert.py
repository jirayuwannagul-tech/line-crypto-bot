import asyncio
from app.utils import state_store
from app.scheduler.runner import tick_once
from app.settings import alerts as alert_settings

# ปรับค่า alert ให้ไว (ทดสอบ)
alert_settings.threshold_pct = 0.5    # แจ้งที่ ±0.5%
alert_settings.hysteresis_pct = 0.1   # กันแกว่ง
alert_settings.cooldown_sec = 3       # คูลดาวน์ 3 วินาที

# ตั้ง baseline ให้ต่ำมาก เพื่อบังคับให้ Alert
state_store.set_baseline("BTC", 10.0)
state_store.set_baseline("ETH", 10.0)

async def main():
    print("⚡ Running tick_once (alert test)")
    # รันทดสอบ BTC
    await tick_once(symbols=["BTC"], dry_run=False)
    # รันทดสอบ ETH
    await tick_once(symbols=["ETH"], dry_run=False)

asyncio.run(main())
