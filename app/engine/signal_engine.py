# app/engine/signal_engine.py
from __future__ import annotations
# =============================================================================
# SIGNAL ENGINE FACADE
# -----------------------------------------------------------------------------
# - จุดศูนย์กลางรันเครื่องวิเคราะห์สัญญาณสำหรับ batch/cron หรือ webhook
# - ใช้ wave_service.analyze_wave เป็น core
# - คืน payload และข้อความสั้น (สำหรับ LINE)
# =============================================================================

from typing import Dict, Optional, Any
import traceback

from app.services.wave_service import analyze_wave, build_brief_message

__all__ = ["SignalEngine", "build_signal_payload", "build_line_text"]

# -----------------------------------------------------------------------------
# Core engine
# -----------------------------------------------------------------------------
class SignalEngine:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, *, xlsx_path: Optional[str] = None, **kwargs):
        self.cfg: Dict[str, Any] = dict(cfg or {})
        if kwargs:
            self.cfg.update(kwargs)
        self.xlsx_path = xlsx_path

    def analyze_symbol(
        self,
        symbol: str,
        tf: str = "1D",
        *,
        profile: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime_cfg = dict(self.cfg)
        if cfg:
            runtime_cfg.update(cfg)
        if profile:
            runtime_cfg["profile"] = profile

        try:
            payload = analyze_wave(symbol, tf=tf, xlsx_path=self.xlsx_path, cfg=runtime_cfg)
            text = build_brief_message(payload)
            return {
                "ok": True,
                "symbol": symbol,
                "tf": tf,
                "profile": runtime_cfg.get("profile", "baseline"),
                "text": text,
                "payload": payload,
                "error": None,
            }
        except Exception as e:
            return {
                "ok": False,
                "symbol": symbol,
                "tf": tf,
                "profile": runtime_cfg.get("profile", "baseline"),
                "text": "",
                "payload": {},
                "error": f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}",
            }

# -----------------------------------------------------------------------------
# Convenience wrappers
# -----------------------------------------------------------------------------
def build_signal_payload(
    symbol: str,
    tf: str = "1D",
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> Dict[str, Any]:
    engine = SignalEngine(cfg=cfg, xlsx_path=xlsx_path)
    return engine.analyze_symbol(symbol, tf, profile=profile, cfg=cfg)

def build_line_text(
    symbol: str,
    tf: str = "1D",
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> str:
    payload = build_signal_payload(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
    if payload.get("ok"):
        return payload.get("text", "")
    err = payload.get("error") or "unknown error"
    return f"❗️Signal error: {err}"
