# app/scheduler/runner.py
"""
Scheduler Runner
เรียกจาก Cloud Scheduler → tick_once → วิเคราะห์/ส่งสัญญาณ 1 รอบ
"""

from typing import Optional, Dict, Any
import logging

from app.services.wave_service import analyze_wave, build_brief_message

logger = logging.getLogger(__name__)


def tick_once(symbols: Optional[list[str]] = None,
              dry_run: bool = False) -> Dict[str, Any]:
    """
    รันการวิเคราะห์สัญลักษณ์ที่กำหนด 1 รอบ
    :param symbols: รายชื่อสัญลักษณ์ (เช่น ["BTCUSDT","ETHUSDT"])
    :param dry_run: ถ้า True → วิเคราะห์แต่ไม่ push LINE
    :return: dict {symbol: payload}
    """
    results: Dict[str, Any] = {}
    symbols = symbols or ["BTCUSDT"]

    for sym in symbols:
        try:
            payload = analyze_wave(sym, "1H")  # ค่า default ใช้ 1H
            msg = build_brief_message(payload)

            results[sym] = {
                "payload": payload,
                "message": msg,
            }

            if not dry_run:
                # TODO: ต่อเข้ากับ notifier_line ถ้าเปิด ALERT_ENABLED
                logger.info("Would push LINE: %s", msg)

        except Exception as e:
            logger.exception("tick_once error for %s", sym)
            results[sym] = {"error": str(e)}

    return results
