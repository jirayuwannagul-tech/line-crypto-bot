from __future__ import annotations

from typing import Optional, Dict, Any
import logging

from app.services.wave_service import analyze_wave, build_brief_message
import os

# ✅ ให้ tests/features/alerts/test_alert.py import ได้
TOP10_SYMBOLS: list[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "TONUSDT", "TRXUSDT", "DOTUSDT",
]

__all__ = ["tick_once", "TOP10_SYMBOLS"]

logger = logging.getLogger(__name__)


def tick_once(symbols: Optional[list[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    เรียกวิเคราะห์ 1 รอบแบบ stateless (ใช้กับ Cloud Scheduler)
    :param symbols: เช่น ["BTCUSDT","ETHUSDT"]; ถ้าไม่ส่งจะใช้ TOP10_SYMBOLS[:1] (BTCUSDT)
    :param dry_run: True = วิเคราะห์อย่างเดียว ไม่ push LINE
    :return: dict per symbol: {payload, message} หรือ {error}
    """
    results: Dict[str, Any] = {}
    syms = symbols or [TOP10_SYMBOLS[0]]  # default = BTCUSDT

    for sym in syms:
        try:
            payload = analyze_wave(sym, os.getenv("JOB_TF","1D"), cfg={"use_live": os.getenv("JOB_USE_LIVE","true").lower()=="true", "live_limit": int(os.getenv("JOB_LIVE_LIMIT","500"))})
            msg = build_brief_message(payload)
            results[sym] = {"payload": payload, "message": msg}
            if not dry_run:
                # ปลอดภัยไว้ก่อน: log แทนการ push จริง (จะต่อ notifier ภายหลัง)
                logger.info("[tick_once] %s -> %s", sym, msg)
        except Exception as e:
            logger.exception("[tick_once] error for %s", sym)
            results[sym] = {"error": str(e)}
    return results
