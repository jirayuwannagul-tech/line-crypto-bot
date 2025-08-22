# app/services/wave_service.py
# -----------------------------------------------------------------------------
# Orchestrator for wave analysis pipeline.
# Load data -> compute scenarios (Dow + Elliott + Fibo + Indicators) -> payload.
#
# Public API:
#   analyze_wave(symbol: str, tf: str = "1D", *, xlsx_path: Optional[str] = None, cfg: Optional[dict] = None) -> dict
#   build_brief_message(payload: dict) -> str     # (optionally used by routers/line_webhook.py)
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Dict, Optional, Any

import pandas as pd

from app.analysis.timeframes import get_data
from app.analysis.scenarios import analyze_scenarios

__all__ = ["analyze_wave", "build_brief_message"]


def _neutral_payload(symbol: str, tf: str, err: Optional[Exception] = None) -> Dict[str, Any]:
    note = f"Data not available: {err}" if err else "Data not available"
    return {
        "symbol": symbol,
        "tf": tf,
        "percent": {"up": 33, "down": 33, "side": 34},
        "levels": {},
        "rationale": [note],
        "meta": {"error": str(err) if err else None},
    }


def analyze_wave(
    symbol: str,
    tf: str = "1D",
    *,
    xlsx_path: Optional[str] = None,
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    End-to-end analysis:
      - Load OHLCV from Excel by timeframe
      - Run scenarios analyzer (Dow + Elliott + Fibo + Indicators)
      - Return payload ready for delivery
    """
    try:
        df: pd.DataFrame = get_data(symbol, tf, xlsx_path=xlsx_path)
    except (FileNotFoundError, ValueError) as e:
        # กรณีไฟล์ Excel ไม่มี / ชีทไม่เจอ → คืน payload กลาง ๆ ใช้งานต่อได้
        return _neutral_payload(symbol, tf, e)

    payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=cfg or {})

    # Attach last price/time for convenience
    if not df.empty:
        last = df.iloc[-1]
        payload["last"] = {
            "timestamp": str(last.get("timestamp", "")),
            "close": float(last.get("close", float("nan"))),
            "high": float(last.get("high", float("nan"))),
            "low": float(last.get("low", float("nan"))),
            "volume": float(last.get("volume", float("nan"))),
        }

    payload["symbol"] = symbol
    payload["tf"] = tf
    return payload


def build_brief_message(payload: Dict[str, object]) -> str:
    """
    Create a short, readable summary suitable for LINE messages.
    Safe to call even if some fields are missing.
    """
    sym = payload.get("symbol", "")
    tf = payload.get("tf", "")
    pct = payload.get("percent", {}) or {}
    up = pct.get("up", "?")
    down = pct.get("down", "?")
    side = pct.get("side", "?")

    levels = (payload.get("levels", {}) or {})
    rh = levels.get("recent_high")
    rl = levels.get("recent_low")
    ema50 = levels.get("ema50")
    ema200 = levels.get("ema200")

    last = payload.get("last", {}) or {}
    px = last.get("close")

    lines = []
    lines.append(f"{sym} ({tf})")
    if isinstance(px, (int, float)):
        lines.append(f"ราคา: {px:,.2f}")
    lines.append(f"ความน่าจะเป็น — ขึ้น {up}% | ลง {down}% | ออกข้าง {side}%")
    if isinstance(rh, (int, float)) and isinstance(rl, (int, float)):
        lines.append(f"กรอบล่าสุด: H {rh:,.2f} / L {rl:,.2f}")
    if isinstance(ema50, (int, float)) and isinstance(ema200, (int, float)):
        lines.append(f"EMA50 {ema50:,.2f} / EMA200 {ema200:,.2f}")

    # Rationale (keep short)
    rationale = payload.get("rationale", []) or []
    if rationale:
        lines.append("เหตุผลย่อ:")
        for r in rationale[:3]:
            lines.append(f"• {r}")

    return "\n".join(lines)
