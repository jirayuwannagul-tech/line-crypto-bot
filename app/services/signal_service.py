# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# อธิบาย:
# - Service layer เรียกใช้ SignalEngine เพื่อสร้างสัญญาณ
# - ทำหน้าที่แปลงผลลัพธ์ให้อยู่ในรูปแบบที่ Jobs/Router ใช้ได้ทันที
# - แยก concern: Engine = logic core, Service = orchestration/formatting
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, Optional, List
import logging

from app.engine.signal_engine import build_signal_payload, build_line_text
from app.adapters import price_provider

logger = logging.getLogger(__name__)

# =============================================================================
# LAYER B) CORE SERVICE FUNCTIONS
# -----------------------------------------------------------------------------
# อธิบาย:
# - ฟังก์ชันใน layer นี้เป็น abstraction ที่เรียบง่าย
# - สามารถใช้ได้ทั้งใน jobs (scheduler) และ routers (LINE webhook)
# =============================================================================

def analyze_and_get_payload(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    วิเคราะห์และคืน payload เต็มจาก SignalEngine
    เหมาะสำหรับ jobs ที่ต้องการบันทึก log หรือเขียนลง DB
    """
    logger.debug(f"Analyzing {symbol} {tf} with profile={profile}")
    payload = build_signal_payload(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
    if not payload.get("ok"):
        logger.error(f"Signal error {symbol} {tf}: {payload.get('error')}")
    return payload


def analyze_and_get_text(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> str:
    """
    วิเคราะห์และคืนข้อความสรุปสั้น (string) อย่างเดียว
    เหมาะสำหรับ push/reply LINE โดยตรง
    """
    return build_line_text(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)


# =============================================================================
# LAYER C) BATCH CONVENIENCE
# -----------------------------------------------------------------------------
# อธิบาย:
# - ใช้รันหลาย symbol/timeframe พร้อมกัน (เช่น ใน job)
# - คืนเป็น list ของผลลัพธ์
# =============================================================================

def analyze_batch(
    symbols: List[str],
    tfs: List[str],
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
    as_text: bool = False,
) -> List[Any]:
    """
    วิเคราะห์หลาย symbol/timeframe พร้อมกัน
    - ถ้า as_text=True คืน list ของ string
    - ถ้า as_text=False คืน list ของ payload dict
    """
    results: List[Any] = []
    for sym in symbols:
        for tf in tfs:
            if as_text:
                results.append(
                    analyze_and_get_text(sym, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
                )
            else:
                results.append(
                    analyze_and_get_payload(sym, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
                )
    return results


# =============================================================================
# LAYER D) PRICE FETCH SERVICE (ใหม่, Binance ผ่าน ccxt)
# -----------------------------------------------------------------------------
# อธิบาย:
# - เพิ่ม service function สำหรับดึงราคาแบบ real-time
# - เรียกจาก adapter.price_provider
# =============================================================================

def fetch_price(symbol: str = "BTC/USDT") -> Optional[float]:
    """
    คืนราคาล่าสุดจาก Binance (float) ผ่าน ccxt
    """
    return price_provider.get_spot_ccxt(symbol)


def fetch_price_text(symbol: str = "BTC/USDT") -> str:
    """
    คืนราคาล่าสุดจาก Binance (string) ใช้ส่งต่อ LINE ได้เลย
    """
    return price_provider.get_spot_text_ccxt(symbol)
