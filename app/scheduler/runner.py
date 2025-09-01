from __future__ import annotations

from typing import Optional, Dict, Any
import logging
import os
from datetime import datetime, timezone

from app.services.idempotency import seen
from app.services.wave_service import analyze_wave, build_brief_message

# ใช้ชื่อ logger เดียวตรงไปตรงมา
logger = logging.getLogger("app.scheduler.runner")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_h)
logger.propagate = True

# ✅ ให้ tests/features/alerts/test_alert.py import ได้
TOP10_SYMBOLS: list[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "TONUSDT", "TRXUSDT", "DOTUSDT",
]

__all__ = ["tick_once", "TOP10_SYMBOLS"]


def tick_once(symbols: Optional[list[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
    """เรียกวิเคราะห์ 1 รอบแบบ stateless (ใช้กับ Cloud Scheduler)

    :param symbols: เช่น ["BTCUSDT","ETHUSDT"]; ถ้าไม่ส่งจะใช้ BTCUSDT
    :param dry_run: True = วิเคราะห์อย่างเดียว ไม่ push LINE
    :return: dict per symbol: {payload, message} หรือ {error}
    """
    tf = os.getenv("JOB_TF", "1D")
    use_live = os.getenv("JOB_USE_LIVE", "true").lower() == "true"
    live_limit = int(os.getenv("JOB_LIVE_LIMIT", "500"))
    logger.info(
        "[tick_once] cfg tf=%s use_live=%s live_limit=%d symbols=%s dry_run=%s",
        tf, use_live, live_limit, symbols, dry_run
    )

    results: Dict[str, Any] = {}
    syms = symbols or [TOP10_SYMBOLS[0]]  # default = BTCUSDT
    cfg = {"use_live": use_live, "live_limit": live_limit}

    # --- Idempotency: กันซ้ำระดับรอบเวลา (bucket 2 นาที) ---
    now = datetime.now(timezone.utc)
    bucket_min = (now.minute // 2) * 2  # 00, 02, 04, ...
    sym_key = ",".join(syms)
    bucket_key = f"tick:{tf}:{sym_key}:{now.hour:02d}:{bucket_min:02d}"
    if seen(bucket_key, ttl_sec=120):
        logger.info("[tick_once] skip duplicated bucket key=%s", bucket_key)
        return {}

    for sym in syms:
        try:
            payload = analyze_wave(sym, tf, cfg=cfg)
            msg = build_brief_message(payload)

            # log สรุปครั้งเดียว
            logger.info("[tick_once] %s -> %s", sym, (msg or "")[:160])
            results[sym] = {"payload": payload, "message": msg}

            if not dry_run:
                # ปลอดภัยไว้ก่อน: log แทนการ push จริง (จะต่อ notifier ภายหลัง)
                logger.info("[tick_once] push (stub) %s", sym)
        except Exception as e:
            logger.exception("[tick_once] error for %s", sym)
            results[sym] = {"error": str(e)}

    return results
