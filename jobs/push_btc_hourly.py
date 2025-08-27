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
from app.analysis.timeframes import get_data
import pandas as pd
from pathlib import Path
import time
try:
    import ccxt
except Exception:
    ccxt = None
from app.analysis import timeframes as tf_mod

def _quick_fill_csv(symbol: str, tf_name: str, limit: int = 1200) -> bool:
    """ดึง OHLCV ล่าสุดผ่าน ccxt แล้วเขียน CSV ไปที่ app/data เพื่อให้ get_data มองเห็น"""
    if ccxt is None:
        return False
    tf_map = {'1H':'1h','4H':'4h','1D':'1d'}
    if tf_name not in tf_map:
        return False
    ex = ccxt.binance()
    try:
        ohlcv = ex.fetch_ohlcv(symbol.replace('USDT','/USDT'), timeframe=tf_map[tf_name], limit=limit)
    except Exception:
        return False
    if not ohlcv:
        return False
    import pandas as _pd
    df = _pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
    out = tf_mod._csv_path(symbol, tf_name)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return True

log = logging.getLogger("jobs.push_btc_hourly")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    return v if v not in (None, "") else default

def _get_bool_env(name: str, default: bool = False) -> bool:
    v = (_env(name, None) or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"): return True
    if v in ("0", "false", "no", "n", "off"): return False
    return default

# [ไฟล์] jobs/push_btc_hourly.py (แทนที่ฟังก์ชัน main ทั้งก้อน)
def main() -> int:
    symbol  = _env("JOB_SYMBOL", "BTCUSDT")
    profile = _env("STRATEGY_PROFILE", "baseline")
    xlsx    = _env("HISTORICAL_XLSX_PATH", None)
    do_broadcast = _get_bool_env("JOB_BROADCAST", False)

    tfs = ["1D", "4H", "1H"]  # ยึด 1D เป็นภาพรวม และแนบบริบท 4H/1H
    texts: dict[str, str] = {}
    rows_count: dict[str, int] = {}

    for tf in tfs:
        try:
            df = get_data(symbol, tf, xlsx_path=xlsx)
            n = 0 if df is None else len(df)
            rows_count[tf] = n
            log.info("DEBUG: %s get_data returned %s rows", tf, n)
        except Exception as e:
            log.error("[%s] Data fetch error: %s", tf, e)
            continue

        if n < 5 or df is None or getattr(df, "empty", False):
            log.warning("[%s] No/low data for %s (len=%s), skip.", tf, symbol, n)
            continue

        try:
            txt = analyze_and_get_text(symbol, tf, profile=profile, cfg={"profile": profile}, xlsx_path=xlsx)
            if txt and str(txt).strip():
                texts[tf] = str(txt).strip()
            else:
                log.warning("[%s] Empty analysis text", tf)
        except Exception as e:
            log.error("[%s] Analyze failed: %s", tf, e)

    # รวมผล: ให้ 1D เป็นสรุปหลัก แล้วตามด้วย 4H/1H แบบย่อ
    if "1D" not in texts and not texts:
        log.error("No signals generated (1D missing and no other TF).")
        return 11

    lines = []
    header = f"📊 {symbol} — Multi-TF Summary (profile={profile})"
    lines.append(header)

    # สรุปหลักจาก 1D
    if "1D" in texts:
        lines.append("\n[1D] สรุปภาพรวม")
        lines.append(texts["1D"])
    else:
        lines.append("\n[1D] สรุปภาพรวม: (ไม่มีข้อมูลหรือวิเคราะห์ไม่สำเร็จ)")

    # แนบบริบทจาก 4H/1H
    for tf in ["4H", "1H"]:
        if tf in texts:
            lines.append(f"\n[{tf}] บริบทระยะสั้น")
            lines.append(texts[tf])
        else:
            n = rows_count.get(tf, 0)
            lines.append(f"\n[{tf}] บริบทระยะสั้น: (ไม่มีสัญญาณ / len={n})")

    final_text = "\n".join(lines)

    # ส่ง LINE
    access = _env("LINE_CHANNEL_ACCESS_TOKEN")
    secret = _env("LINE_CHANNEL_SECRET")
    if not access or not secret:
        log.error("Missing LINE credentials (LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET)")
        return 2

    client = LineDelivery(access, secret)

    # ถ้าไม่กำหนด LINE_DEFAULT_TO ให้บังคับ broadcast
    if not do_broadcast and not _env("LINE_DEFAULT_TO"):
        do_broadcast = True

    if do_broadcast:
        log.info("Broadcasting multi-TF signal…")
        resp = client.broadcast_text(final_text)
    else:
        to_id = _env("LINE_DEFAULT_TO")
        if not to_id:
            log.error("Missing LINE_DEFAULT_TO for push")
            return 3
        log.info("Pushing multi-TF signal to %s …", to_id)
        resp = client.push_text(to_id, final_text)

    if not resp.get("ok"):
        log.error("LINE send failed: %s", resp)
        return 1

    log.info("Job done.")
    return 0
