# app/services/signal_service.py
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
    text = build_line_text(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
    return text

# app/engine/signal_engine.py

def build_line_text(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> str:
    payload = build_signal_payload(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)

    if not payload.get("ok"):
        return f"❌ Error: {payload.get('error','unknown')}"

    sig = payload["signal"]
    probs = sig.get("probabilities", {})
    bias = sig.get("bias", "neutral")
    entry = sig.get("entry") or "-"
    sl    = sig.get("sl") or "-"
    tp    = sig.get("tp") or "-"
    last_price = sig.get("last_price", None)

    # สรุป %UP/DOWN/SIDE
    up_p   = probs.get("up", 0) * 100
    down_p = probs.get("down", 0) * 100
    side_p = probs.get("side", 0) * 100

    lines = []
    header = f"📊 {symbol} {tf} — สรุปสัญญาณ"
    if last_price:
        header += f"\nราคา: {last_price:,.2f} USDT"
    lines.append(header)
    lines.append(f"UP {up_p:.0f}% | DOWN {down_p:.0f}% | SIDE {side_p:.0f}%")
    lines.append("")
    lines.append(f"🎯 ทางเลือก (bias): {bias.upper()}")
    lines.append(f"• Entry: {entry}")
    lines.append(f"• SL: {sl}")
    lines.append(f"• TP: {tp}")
    lines.append("")

    # แสดงเหตุผลจาก indicators/patterns (top 3)
    reasons = sig.get("reasons", [])[:3]
    if reasons:
        lines.append("ℹ️ เหตุผลหลัก:")
        for r in reasons:
            msg = r.get("message","")
            code = r.get("code","")
            lines.append(f"• [{code}] {msg}")

    return "\n".join(lines)


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
                results.append(analyze_and_get_text(sym, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path))
            else:
                results.append(analyze_and_get_payload(sym, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path))
    return results
