# test_alert.py
import asyncio
from app.scheduler.runner import tick_once
from app.settings.alerts import alert_settings
from app.utils import state_store

async def main():
    # ปรับ alert ให้ไว (เพื่อทดสอบ)
    alert_settings.threshold_pct = 0.5    # แจ้งที่ ±0.5%
    alert_settings.hysteresis_pct = 0.1   # กันแกว่ง
    alert_settings.cooldown_sec = 3       # คูลดาวน์ 3 วินาที

    # บังคับ baseline BTC/ETH ให้ต่ำมาก เพื่อให้ trigger แน่ ๆ
    state_store.set_baseline("BTC", 10.0)
    state_store.set_baseline("ETH", 10.0)

    print("⚡ Running tick_once (alert test)")
    await tick_once(dry_run=False)  # ยิง alert จริงเข้า LINE

if __name__ == "__main__":
    asyncio.run(main())
