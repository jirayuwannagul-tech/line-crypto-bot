# jobs/push_btc_hourly.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# ใช้เป็น job เรียกตามเวลา (เช่น cron/Render scheduler):
# - วิเคราะห์สัญญาณด้วยโปรไฟล์ที่เลือก
# - ส่งข้อความผลลัพธ์ไป LINE แบบ push (หรือ broadcast ได้ผ่าน ENV)
#
# ENV ที่เกี่ยวข้อง:
#   LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, LINE_DEFAULT_TO
#   JOB_SYMBOL            (default: BTCUSDT)
#   JOB_TF                (default: 1H)
#   STRATEGY_PROFILE      (default: baseline)
#   HISTORICAL_XLSX_PATH  (optional override)
#   JOB_BROADCAST         (set "1" เพื่อ broadcast แทน push)
#
# วิธีรัน (ตัวอย่าง):
#   python -m jobs.push_btc_hourly
#   # หรือ
#   python jobs/push_btc_hourly.py
# =============================================================================

from __future__ import annotations
import os
import logging
import traceback

from app.services.signal_service import analyze_and_get_text
from app.adapters.delivery_line import LineDelivery
from app.analysis.timeframes import get_data  # ✅ เพิ่ม: ใช้เช็กข้อมูลก่อนวิเคราะห์

log = logging.getLogger("jobs.push_btc_hourly")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# =============================================================================
# LAYER B) ENV HELPERS
# =============================================================================
def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    return v if v not in (None, "") else default

def _get_bool_env(name: str, default: bool = False) -> bool:
    v = (_env(name, None) or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"): return True
    if v in ("0", "false", "no", "n", "off"): return False
    return default

# =============================================================================
# LAYER C) MAIN JOB LOGIC
# =============================================================================
def main() -> int:
    # --- config จาก ENV (มีค่า default ที่ปลอดภัย)
    symbol  = _env("JOB_SYMBOL", "BTCUSDT")
    tf      = _env("JOB_TF", "1H")
    profile = _env("STRATEGY_PROFILE", "baseline")
    xlsx    = _env("HISTORICAL_XLSX_PATH", None)
    do_broadcast = _get_bool_env("JOB_BROADCAST", False)

    # --- เช็กข้อมูลก่อน (กัน DataFrame ว่าง → IndexError)
    try:
        df = get_data(symbol, tf, xlsx_path=xlsx)  # อนุญาตให้ provider ภายในตัดสินใจว่าจะใช้ API/CSV/Excel
    except Exception as e:
        log.error("Data fetch error: %s", e)
        log.debug("Traceback:\n%s", traceback.format_exc())
        return 20

    if df is None or getattr(df, "empty", False) or len(df) < 5:
        log.error("No data for %s %s (len=%s). Abort analyze.", symbol, tf, 0 if df is None else len(df))
        return 21

    # --- สร้างข้อความสรุปจาก service (profile-aware)
    cfg = {"profile": profile}
    log.info("Analyzing %s %s with profile=%s", symbol, tf, profile)

    try:
        text = analyze_and_get_text(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx)
    except Exception as e:
        log.error("Analyze failed: %s", e)
        log.debug("Traceback:\n%s", traceback.format_exc())
        return 10

    if not text or not str(text).strip():
        log.error("Empty analysis text; abort sending.")
        return 11

    # --- ตรวจ credentials สำหรับ LINE
    access = _env("LINE_CHANNEL_ACCESS_TOKEN")
    secret = _env("LINE_CHANNEL_SECRET")
    if not access or not secret:
        log.error("Missing LINE credentials (LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET)")
        return 2

    client = LineDelivery(access, secret)

    # --- ส่งข้อความ
    # ถ้าไม่กำหนด LINE_DEFAULT_TO ให้บังคับใช้ broadcast เพื่อป้องกันตกหล่น
    if not do_broadcast and not _env("LINE_DEFAULT_TO"):
        do_broadcast = True

    if do_broadcast:
        log.info("Broadcasting signal…")
        resp = client.broadcast_text(text)
    else:
        to_id = _env("LINE_DEFAULT_TO")
        if not to_id:
            log.error("Missing LINE_DEFAULT_TO for push")
            return 3
        log.info("Pushing to %s …", to_id)
        resp = client.push_text(to_id, text)

    # --- ตรวจสอบผลส่ง
    if not resp.get("ok"):
        log.error("LINE send failed: %s", resp)
        return 1

    log.info("Job done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
