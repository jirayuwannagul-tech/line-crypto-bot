# jobs/push_btc_hourly.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# ใช้เป็น job เรียกตามเวลา (เช่น cron/Render scheduler):
# - วิเคราะห์สัญญาณหลาย TF (1D, 4H, 1H)
# - สรุปภาพรวมยึด 1D แล้วแนบบริบท 4H/1H
# - ส่งข้อความผลลัพธ์ไป LINE (push/broadcast)
#
# ENV:
#   LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, LINE_DEFAULT_TO
#   JOB_SYMBOL            (default: BTCUSDT)
#   STRATEGY_PROFILE      (default: baseline)
#   HISTORICAL_XLSX_PATH  (optional override)
#   JOB_BROADCAST         ("1" เพื่อ broadcast)
#
# Dry-run: ตั้ง
#   export LINE_CHANNEL_ACCESS_TOKEN=dummy
#   export LINE_CHANNEL_SECRET=dummy
#   export JOB_BROADCAST=1
# แล้วรัน Python โมดูลนี้ จะพิมพ์ข้อความออกจอแทนการส่ง LINE
# =============================================================================

from __future__ import annotations
import os
import logging
import traceback
from pathlib import Path

import pandas as pd

from app.services.signal_service import analyze_and_get_text
from app.adapters.delivery_line import LineDelivery
from app.analysis.timeframes import get_data
from app.analysis import timeframes as tf_mod

try:
    import ccxt
except Exception:
    ccxt = None

log = logging.getLogger("jobs.push_btc_hourly")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


# =============================================================================
# Helpers
# =============================================================================
def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    return v if v not in (None, "") else default

def _get_bool_env(name: str, default: bool = False) -> bool:
    v = (_env(name, None) or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"): return True
    if v in ("0", "false", "no", "n", "off"): return False
    return default

def _quick_fill_csv(symbol: str, tf_name: str, limit: int = 1200) -> bool:
    """ดึง OHLCV ผ่าน ccxt แล้วเขียน CSV ไปที่ app/data เพื่อให้ get_data ใช้ต่อ (รองรับ 1H/4H/1D)"""
    if ccxt is None:
        log.warning("ccxt not available; skip quick fill.")
        return False
    tf_map = {"1H": "1h", "4H": "4h", "1D": "1d"}
    if tf_name not in tf_map:
        return False
    try:
        ex = ccxt.binance()
        symbol_ccxt = symbol.replace("USDT", "/USDT")
        ohlcv = ex.fetch_ohlcv(symbol_ccxt, timeframe=tf_map[tf_name], limit=limit)
        if not ohlcv:
            return False
        df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
        out = tf_mod._csv_path(symbol, tf_name)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        log.info("Quick-filled CSV: %s (%s rows)", out, len(df))
        return True
    except Exception as e:
        log.warning("quick_fill failed for %s %s: %s", symbol, tf_name, e)
        return False


# =============================================================================
# Main
# =============================================================================
def main() -> int:
    symbol  = _env("JOB_SYMBOL", "BTCUSDT")
    profile = _env("STRATEGY_PROFILE", "baseline")
    xlsx    = _env("HISTORICAL_XLSX_PATH", None)
    do_broadcast = _get_bool_env("JOB_BROADCAST", False)

    # เรียงลำดับให้ 1D มาก่อน เพื่อใช้เป็น "สรุปภาพรวม"
    tfs = ["1D", "4H", "1H"]

    texts: dict[str, str] = {}
    rows_count: dict[str, int] = {}

    # --- วนดึง/วิเคราะห์ทีละ TF ---
    for tf in tfs:
        try:
            df = get_data(symbol, tf, xlsx_path=xlsx)
            n = 0 if df is None else len(df)
            rows_count[tf] = n
            log.info("DEBUG: %s get_data returned %s rows", tf, n)
        except Exception as e:
            log.error("[%s] Data fetch error: %s", tf, e)
            log.debug("Traceback:\n%s", traceback.format_exc())
            continue

        # ถ้าข้อมูลน้อย ลอง quick-fill แล้วโหลดใหม่
        if n < 5 or df is None or getattr(df, "empty", False):
            log.warning("[%s] No/low data (len=%s). Try quick fill via ccxt…", tf, n)
            if _quick_fill_csv(symbol, tf, limit=1200):
                try:
                    df = get_data(symbol, tf, xlsx_path=xlsx)
                    n = 0 if df is None else len(df)
                    rows_count[tf] = n
                    log.info("DEBUG(after quick fill): %s get_data returned %s rows", tf, n)
                except Exception as e:
                    log.error("[%s] Data fetch error after quick fill: %s", tf, e)
                    continue

        # ข้าม TF ที่ยังไม่มีข้อมูล
        if n < 5 or df is None or getattr(df, "empty", False):
            log.warning("[%s] still no data; skip.", tf)
            continue

        # วิเคราะห์ข้อความสรุปสำหรับ TF นั้น ๆ
        try:
            txt = analyze_and_get_text(symbol, tf, profile=profile, cfg={"profile": profile}, xlsx_path=xlsx)
            if txt and str(txt).strip():
                texts[tf] = str(txt).strip()
            else:
                log.warning("[%s] Empty analysis text", tf)
        except Exception as e:
            log.error("[%s] Analyze failed: %s", tf, e)
            log.debug("Traceback:\n%s", traceback.format_exc())

    # --- รวมผล: ยึด 1D เป็นสรุปหลัก + แนบบริบท 4H/1H ---
    if "1D" not in texts and not texts:
        log.error("No signals generated (1D missing and no other TF).")
        return 11

    lines = []
    header = f"📊 {symbol} — Multi-TF Summary (profile={profile})"
    lines.append(header)

    # 1D = ภาพรวมหลัก
    if "1D" in texts:
        lines.append("\n[1D] สรุปภาพรวม")
        lines.append(texts["1D"])
    else:
        lines.append("\n[1D] สรุปภาพรวม: (ไม่มีข้อมูลหรือวิเคราะห์ไม่สำเร็จ)")

    # 4H/1H = บริบทระยะสั้น
    for tf in ["4H", "1H"]:
        if tf in texts:
            lines.append(f"\n[{tf}] บริบทระยะสั้น")
            lines.append(texts[tf])
        else:
            n = rows_count.get(tf, 0)
            lines.append(f"\n[{tf}] บริบทระยะสั้น: (ไม่มีสัญญาณ / len={n})")

    final_text = "\n".join(lines)

    # --- LINE credentials ---
    access = _env("LINE_CHANNEL_ACCESS_TOKEN")
    secret = _env("LINE_CHANNEL_SECRET")
    if not access or not secret:
        log.error("Missing LINE credentials (LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET)")
        return 2

    # --- Dry-run: ใช้ dummy token เพื่อพิมพ์ข้อความออกจอแทนการส่ง LINE ---
    if access == "dummy" and secret == "dummy":
        print("\n===== DRY RUN (dummy token) =====")
        print(final_text)
        return 0

    client = LineDelivery(access, secret)

    # ไม่มี LINE_DEFAULT_TO → บังคับ broadcast ป้องกันตกหล่น
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


if __name__ == "__main__":
    raise SystemExit(main())
