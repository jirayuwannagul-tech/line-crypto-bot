# =============================================================================
# LAYER A) OVERVIEW (FastAPI Router: On-demand Analysis)
# -----------------------------------------------------------------------------
# - Endpoint: /analyze/analyze   (เพราะ main include_router(..., prefix="/analyze"))
# - โหมด live ดึงข้อมูลจริงผ่าน wave_service (ccxt/binance wrapper)
# - mode="text"     -> คืนข้อความสรุป (พร้อมส่ง LINE ได้)
# - mode="payload"  -> คืน payload เต็ม (percent/levels/entry/sl/tp/notes)
# =============================================================================

from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Query, HTTPException

from app.services.wave_service import analyze_wave, build_brief_message

router = APIRouter(tags=["analyze"])

_VALID_TF = {"1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W"}


def _norm_symbol(sym: str) -> str:
    # ตัวอย่างอินพุต: btcusdt, BTC/USDT, BTC:USDT -> BTCUSDT
    s = (sym or "").strip().upper()
    s = s.replace(":", "/").replace("-", "/")
    parts = [p for p in s.split("/") if p]
    if len(parts) == 2:
        return f"{parts[0]}{parts[1]}"
    return s


def _norm_tf(tf: str) -> str:
    return (tf or "").strip().upper()


@router.get(
    "/analyze",
    summary="วิเคราะห์สัญญาณแบบ on-demand",
    description=(
        "เรียกวิเคราะห์สัญญาณสำหรับสัญลักษณ์และ timeframe ที่กำหนด (โหมด LIVE)\n\n"
        "ตัวอย่าง:\n"
        "• /analyze?symbol=BTCUSDT&tf=1D&mode=text\n"
        "• /analyze?symbol=ETHUSDT&tf=4H&mode=payload\n"
    ),
)
def analyze_endpoint(
    symbol: str = Query("BTCUSDT", description="เช่น BTCUSDT, ETHUSDT หรือรูปแบบ BTC/USDT"),
    tf: str = Query("1D", description="หนึ่งใน: 1M,5M,15M,30M,1H,4H,1D,1W"),
    mode: str = Query("text", description="text | payload"),
    live_limit: int = Query(500, description="จำนวนแท่งสูงสุดที่ดึงจาก live provider (เช่น Binance)"),
) -> Dict[str, Any]:
    """
    คืน {"ok": True, "mode": "...", "symbol": "...", "tf": "...", "payload"/"text": ...}
    เส้นทางจริงบนเซิร์ฟเวอร์ = /analyze/analyze (เพราะมี prefix จาก main)
    """
    if mode not in ("text", "payload"):
        raise HTTPException(status_code=400, detail="mode must be 'text' or 'payload'")

    sym = _norm_symbol(symbol)
    tf_u = _norm_tf(tf)
    if tf_u not in _VALID_TF:
        raise HTTPException(status_code=400, detail=f"invalid tf '{tf}'. allowed: {sorted(_VALID_TF)}")

    # โหมด LIVE: เรียก wave_service โดยตรง
    cfg = {"use_live": True, "live_limit": int(live_limit)}
    payload = analyze_wave(sym, tf_u, cfg=cfg)

    if mode == "text":
        text = build_brief_message(payload)
        return {
            "ok": True,
            "mode": "text",
            "symbol": sym,
            "tf": tf_u,
            "text": text,
        }

    # mode == "payload"
    return {
        "ok": True,
        "mode": "payload",
        "symbol": sym,
        "tf": tf_u,
        "payload": payload,
    }


@router.get(
    "/analyze/wave",
    summary="(Alias) วิเคราะห์สัญญาณแบบ on-demand (เส้นทางเดิม)",
    description="Alias ของ /analyze เพื่อรองรับ client เดิม ใช้พารามิเตอร์เดียวกันทั้งหมด",
)
def analyze_wave_alias(
    symbol: str = Query("BTCUSDT", description="เช่น BTCUSDT, ETHUSDT หรือรูปแบบ BTC/USDT"),
    tf: str = Query("1D", description="หนึ่งใน: 1M,5M,15M,30M,1H,4H,1D,1W"),
    mode: str = Query("text", description="text | payload"),
    live_limit: int = Query(500, description="จำนวนแท่งสูงสุดที่ดึงจาก live provider"),
) -> Dict[str, Any]:
    # reuse handler หลัก
    return analyze_endpoint(symbol=symbol, tf=tf, mode=mode, live_limit=live_limit)

@router.get(
    "/sample",
    summary="ตัวอย่างผลวิเคราะห์อย่างย่อ (alias เดิม)",
    description="คืนผลวิเคราะห์ค่าเริ่มต้น symbol=BTCUSDT, tf=1D, mode=text",
)
def analyze_sample():
    return analyze_endpoint(symbol="BTCUSDT", tf="1D", mode="text", live_limit=200)
