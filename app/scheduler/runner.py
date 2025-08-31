from __future__ import annotations

from typing import Optional, Dict, Any
import os
import logging

from app.services.wave_service import analyze_wave, build_brief_message

# Logger สำหรับโมดูลนี้
logger = logging.getLogger("app.scheduler.runner")

# ✅ ให้ tests/features/alerts/test_alert.py import ได้
TOP10_SYMBOLS: list[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "TONUSDT", "TRXUSDT", "DOTUSDT",
]

__all__ = ["tick_once", "TOP10_SYMBOLS"]


def tick_once(symbols: Optional[list[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    เรียกวิเคราะห์ 1 รอบแบบ stateless (ใช้กับ Cloud Scheduler)
    :param symbols: เช่น ["BTCUSDT","ETHUSDT"]; ถ้าไม่ส่งจะใช้ TOP10_SYMBOLS[:1] (BTCUSDT)
    :param dry_run: True = วิเคราะห์อย่างเดียว ไม่ push LINE
    :return: dict per symbol: {payload, message} หรือ {error}
    """
    results: Dict[str, Any] = {}
    syms = symbols or [TOP10_SYMBOLS[0]]  # default = BTCUSDT

    tf = os.getenv("JOB_TF", "1D")
    use_live = os.getenv("JOB_USE_LIVE", "true").lower() == "true"
    live_limit = int(os.getenv("JOB_LIVE_LIMIT", "500"))

    # กำหนด config หนึ่งครั้ง ใช้ร่วมกันได้
    cfg = {"use_live": use_live, "live_limit": live_limit}

    logger.info("[tick_once] cfg tf=%s use_live=%s live_limit=%d symbols=%s",
                tf, use_live, live_limit, ",".join(syms))

    for sym in syms:
        try:
            payload = analyze_wave(sym, tf, cfg=cfg)
            msg = build_brief_message(payload)
            logger.info("[tick_once] %s tf=%s -> %s", sym, tf, (msg or "")[:160])

            results[sym] = {"payload": payload, "message": msg}

            if not dry_run:
                # TODO: ภายหลังต่อ notifier เพื่อ push LINE จริง
                logger.info("[tick_once] would push -> %s", msg)
        except Exception as e:
            logger.exception("[tick_once] error for %s", sym)
            results[sym] = {"error": str(e)}

    return results
