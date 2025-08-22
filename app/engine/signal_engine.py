# app/engine/signal_engine.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# อธิบาย:
# - จุดศูนย์กลาง “รันเครื่องวิเคราะห์สัญญาณ” สำหรับงาน batch/cron หรือ webhook
# - ลำดับงาน: get_data → suggest_trade (profile‑aware) → สร้าง payload สำหรับส่ง LINE
# - คงความเข้ากันได้กับของเดิม โดยเพิ่มตัวเลือก profile แบบ optional
# =============================================================================

from __future__ import annotations
from typing import Dict, Optional, Any

import os
import traceback

import pandas as pd

from app.analysis.timeframes import get_data
from app.analysis.entry_exit import suggest_trade, format_trade_text

# =============================================================================
# LAYER B) CONFIG LOADING (SAFE DEFAULTS)
# -----------------------------------------------------------------------------
# อธิบาย:
# - อ่าน ENV เล็กน้อยเพื่อให้รันได้ในทั้ง dev/prod โดยไม่พังถ้าไม่มีค่า
# - profile: baseline | cholak | chinchot (ดีฟอลต์ baseline)
# =============================================================================

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v if v is not None and v != "" else default

DEFAULT_PROFILE = _env("STRATEGY_PROFILE", "baseline")  # ใช้ถ้า caller ไม่ส่งมา

# =============================================================================
# LAYER C) CORE ENGINE (SIMPLE FACADE)
# -----------------------------------------------------------------------------
# อธิบาย:
# - ฟาซาดเรียบง่ายสำหรับสร้าง “สัญญาณ” หนึ่งชุดต่อ symbol/timeframe
# - คืน dict สำหรับไปใช้ต่อ (เช่นใน Services/Router หรือ Jobs)
# - ไม่ผูกกับ LINE โดยตรง ให้ส่วน caller ตัดสินใจว่าจะส่งอย่างไร
# =============================================================================

class SignalEngine:
    def __init__(self, *, xlsx_path: Optional[str] = None):
        """
        xlsx_path: ทางเลือก ถ้าต้อง override ไฟล์ historical.xlsx
        """
        self.xlsx_path = xlsx_path

    # --- public API -----------------------------------------------------------
    def analyze_symbol(
        self,
        symbol: str,
        tf: str,
        *,
        profile: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        วิเคราะห์สัญญาณหนึ่งชุดและคืน payload พร้อมข้อความสำหรับนำไปส่ง LINE

        Returns
        -------
        {
          "ok": bool,
          "symbol": str,
          "tf": str,
          "profile": str,
          "text": str,            # สรุปข้อความสั้น สำหรับ LINE
          "trade": Dict,          # payload เต็มจาก suggest_trade()
          "error": Optional[str], # ถ้า ok=False จะมีข้อความ error
        }
        """
        cfg = cfg or {}
        use_profile = (profile or cfg.get("profile") or DEFAULT_PROFILE) or "baseline"

        try:
            # 1) ดึงข้อมูล OHLCV
            df = get_data(symbol, tf, xlsx_path=self.xlsx_path)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {
                    "ok": False,
                    "symbol": symbol,
                    "tf": tf,
                    "profile": use_profile,
                    "text": "",
                    "trade": {},
                    "error": "No data loaded for symbol/timeframe.",
                }

            # 2) วิเคราะห์ entry/exit (ภายในจะเรียก scenarios แบบ profile‑aware)
            trade = suggest_trade(
                df,
                symbol=symbol,
                tf=tf,
                cfg={**cfg, "profile": use_profile},
            )

            # 3) สร้างข้อความสรุป (สำหรับ LINE หรือ log)
            text = format_trade_text(trade)

            return {
                "ok": True,
                "symbol": symbol,
                "tf": tf,
                "profile": use_profile,
                "text": text,
                "trade": trade,
                "error": None,
            }

        except Exception as e:
            return {
                "ok": False,
                "symbol": symbol,
                "tf": tf,
                "profile": use_profile,
                "text": "",
                "trade": {},
                "error": f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}",
            }

# =============================================================================
# LAYER D) CONVENIENCE FUNCTIONS (BACKWARD‑COMPATIBLE)
# -----------------------------------------------------------------------------
# อธิบาย:
# - เผื่อโค้ดเดิมเรียกใช้ฟังก์ชันแบบ procedural
# - ทั้งสองฟังก์ชันด้านล่างเป็น wrapper รอบ SignalEngine.analyze_symbol()
# =============================================================================

def build_signal_payload(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wrapper ใช้งานง่าย: คืน payload เดียวกับ SignalEngine.analyze_symbol()
    """
    engine = SignalEngine(xlsx_path=xlsx_path)
    return engine.analyze_symbol(symbol, tf, profile=profile, cfg=cfg)

def build_line_text(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> str:
    """
    คืนข้อความสรุป (string) อย่างเดียว — เหมาะสำหรับ push ผ่าน LINE ทันที
    """
    payload = build_signal_payload(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
    if payload.get("ok"):
        return payload.get("text", "")
    # ถ้า error ให้สรุปสั้น ๆ (อย่าทิ้งเงียบ)
    err = payload.get("error") or "unknown error"
    return f"❗️Signal error: {err}"
