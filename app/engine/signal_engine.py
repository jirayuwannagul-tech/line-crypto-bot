# app/engine/signal_engine.py
from __future__ import annotations
# =============================================================================
# SIGNAL ENGINE FACADE
# -----------------------------------------------------------------------------
# - จุดศูนย์กลางรันเครื่องวิเคราะห์สัญญาณสำหรับงาน batch/cron หรือ webhook
# - ลำดับงาน: get_data → suggest_trade (profile-aware) → สร้าง payload/ข้อความ
# - รักษา backward compatibility กับโค้ดเดิม
# =============================================================================

from typing import Dict, Optional, Any
import os
import traceback
import pandas as pd

from app.analysis.timeframes import get_data
from app.analysis.entry_exit import suggest_trade, format_trade_text

__all__ = ["SignalEngine", "build_signal_payload", "build_line_text"]

# -----------------------------------------------------------------------------
# Config helpers
# -----------------------------------------------------------------------------
def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v if v is not None and v != "" else default

DEFAULT_PROFILE = _env("STRATEGY_PROFILE", "baseline")  # fallback ถ้า caller ไม่ส่งมา

# -----------------------------------------------------------------------------
# Core engine
# -----------------------------------------------------------------------------
class SignalEngine:
    def __init__(self, *, xlsx_path: Optional[str] = None):
        """
        xlsx_path: override เส้นทางไฟล์ historical.xlsx ได้ถ้าต้องการ
        """
        self.xlsx_path = xlsx_path

    def analyze_symbol(
        self,
        symbol: str,
        tf: str,
        *,
        profile: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        วิเคราะห์สัญญาณหนึ่งชุดและคืน payload พร้อมข้อความสำหรับส่ง LINE

        Returns:
        {
          "ok": bool,
          "symbol": str,
          "tf": str,
          "profile": str,
          "text": str,    # ข้อความสรุปสั้น
          "trade": Dict,  # payload เต็มจาก suggest_trade()
          "error": Optional[str],
        }
        """
        cfg = cfg or {}
        use_profile = (profile or cfg.get("profile") or DEFAULT_PROFILE) or "baseline"

        try:
            # 1) Load OHLCV
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

            # 2) Build trade suggestion (ภายใน profile-aware)
            trade = suggest_trade(
                df,
                symbol=symbol,
                tf=tf,
                cfg={**cfg, "profile": use_profile},
            )

            # 3) Compose short text
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

# -----------------------------------------------------------------------------
# Convenience wrappers (backward‑compatible)
# -----------------------------------------------------------------------------
def build_signal_payload(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Wrapper: คืน payload เดียวกับ SignalEngine.analyze_symbol()"""
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
    """คืนข้อความสรุปอย่างเดียว — เหมาะสำหรับ push ผ่าน LINE"""
    payload = build_signal_payload(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
    if payload.get("ok"):
        return payload.get("text", "")
    err = payload.get("error") or "unknown error"
    return f"❗️Signal error: {err}"
