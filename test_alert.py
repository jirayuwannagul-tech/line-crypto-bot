# test_alert.py
import asyncio
from app.scheduler.runner import tick_once
from app.settings import alerts as alert_settings
from app.utils import state_store

# ===== ปรับค่าการแจ้งเตือนให้ไว =====
alert_settings.threshold_pct = 0.5    # แจ้งที่ ±0.5%
alert_settings.hysteresis_pct = 0.1   # กันแกว่ง
alert_settings.cooldown_sec = 3       # คูลดาวน์ 3 วินาที

# ===== บังคับ baseline ให้ต่ำมาก เพื่อบังคับให้แจ้งเตือน =====
state_store.set_baseline("BTC", 10.0)
state_store.set_baseline("ETH", 10.0)

async def main():
    print("⚡ Running tick_once (alert test BTC + ETH)")
    await tick_once(dry_run=False)   # จะส่งแจ้งเตือนเข้า LINE ถ้าเกิน threshold

if __name__ == "__main__":
    asyncio.run(main())
