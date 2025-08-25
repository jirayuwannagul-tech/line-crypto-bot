# worker.py
import os
import sys
import argparse
import asyncio
import logging
from datetime import datetime, timezone

from app.analysis.timeframes import (
    start_timeframe_service,
    stop_timeframe_service,
    get_last_updated,
)

# ====== CONFIG (อ่านจาก ENV) ======
PAIRS = [
    # คอมม่าแยกหลาย TF ได้ เช่น BTCUSDT:1m,BTCUSDT:1h,ETHUSDT:1h
    # ถ้าตั้ง ENV WORKER_PAIRS จะ override รายการนี้
    # ตัวอย่าง: WORKER_PAIRS="BTCUSDT:1m,BTCUSDT:1h"
]
_env_pairs = os.getenv("WORKER_PAIRS", "").strip()
if _env_pairs:
    for item in _env_pairs.split(","):
        sym, tf = item.strip().split(":")
        PAIRS.append((sym.upper(), tf))
else:
    # ดีฟอลต์ถ้าไม่ได้ตั้ง
    PAIRS = [("BTCUSDT", "1m"), ("BTCUSDT", "1h"), ("BTCUSDT", "1D")]

HEARTBEAT_SECONDS = int(os.getenv("HEARTBEAT_SECONDS", "60"))
# โหมดเร่งทดสอบ: บังคับให้รออัปเดตรอบถัดไปสั้นลง (วินาที) ถ้าเป็น 0 = ปิด
DEBUG_NEXTBAR_SECONDS = int(os.getenv("DEBUG_NEXTBAR_SECONDS", "0"))

# คอนฟิกฝั่ง timeframes (อ่านโดย get_data/fetch ภายใน)
REALTIME = os.getenv("REALTIME", "").strip()
PROVIDERS = os.getenv("PROVIDERS", "binance")
REALTIME_LIMIT = os.getenv("REALTIME_LIMIT", "1000")
REALTIME_TIMEOUT = os.getenv("REALTIME_TIMEOUT", "12")
BACKGROUND_WARM_LIMIT = os.getenv("BACKGROUND_WARM_LIMIT", "1000")
BACKGROUND_CYCLE_LIMIT = os.getenv("BACKGROUND_CYCLE_LIMIT", "300")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("worker")


def print_config():
    """พิมพ์คอนฟิกทั้งหมดให้ดูแล้วออกจากโปรแกรม"""
    print("\n=== Worker Configuration ===")
    print(f"PAIRS: {', '.join([f'{s}:{t}' for s,t in PAIRS])}")
    print(f"HEARTBEAT_SECONDS: {HEARTBEAT_SECONDS}")
    print(f"DEBUG_NEXTBAR_SECONDS: {DEBUG_NEXTBAR_SECONDS}  (0=disabled)")
    print("=== Timeframes Module Environment ===")
    print(f"REALTIME: {REALTIME!r}  (set '1' to enable realtime fetch)")
    print(f"PROVIDERS: {PROVIDERS}")
    print(f"REALTIME_LIMIT: {REALTIME_LIMIT}")
    print(f"REALTIME_TIMEOUT: {REALTIME_TIMEOUT}s")
    print(f"BACKGROUND_WARM_LIMIT: {BACKGROUND_WARM_LIMIT}")
    print(f"BACKGROUND_CYCLE_LIMIT: {BACKGROUND_CYCLE_LIMIT}")
    print("============================\n")


async def heartbeat():
    """พิมพ์สถานะล่าสุดของแต่ละ (symbol, tf) ลง log เป็นระยะ"""
    while True:
        lines = ["Heartbeat — last updated:"]
        for sym, tf in PAIRS:
            ts = get_last_updated(sym, tf)
            if ts:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                lines.append(f"  • {sym}-{tf}: {dt}")
            else:
                lines.append(f"  • {sym}-{tf}: (no data yet)")
        log.info("\n" + "\n".join(lines))
        await asyncio.sleep(HEARTBEAT_SECONDS)


async def main(args):
    # โหมดดูคอนฟิกแล้วออก
    if args.config:
        print_config()
        return

    # โหมดทดสอบเร็ว: บังคับช่วงรอขอบแท่งผ่าน ENV ให้ timeframes ใช้
    if DEBUG_NEXTBAR_SECONDS > 0:
        # timeframes จะอ่านค่านี้ (เราจะใช้ชื่อ ENV นี้ใน timeframes.py ด้วย)
        os.environ["FORCE_NEXTBAR_SECONDS"] = str(DEBUG_NEXTBAR_SECONDS)
        log.info(f"DEBUG: force next-bar wait = {DEBUG_NEXTBAR_SECONDS}s")

    await start_timeframe_service(PAIRS)
    hb_task = asyncio.create_task(heartbeat())

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        log.info("Worker cancelled, shutting down...")
    finally:
        hb_task.cancel()
        await stop_timeframe_service()
        log.info("Worker stopped cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Line Crypto Bot Worker")
    parser.add_argument("--config", action="store_true", help="แสดงคอนฟิกทั้งหมดแล้วออก")
    args = parser.parse_args()
    asyncio.run(main(args))
