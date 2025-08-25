# app/services/wave_service.py
# -----------------------------------------------------------------------------
# Orchestrator for wave analysis pipeline.
# Load data -> compute scenarios (Dow + Elliott + Fibo + Indicators) -> payload.
# -----------------------------------------------------------------------------
from __future__ import annotations

from typing import Dict, Optional, Any
import pandas as pd
import math

from app.analysis.timeframes import get_data
# 🔧 ใช้ logic layer
from app.logic.scenarios import analyze_scenarios

__all__ = ["analyze_wave", "build_brief_message"]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
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

def _merge_dict(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Recursive merge b over a."""
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def analyze_wave(
    symbol: str,
    tf: str = "1D",
    *,
    xlsx_path: Optional[str] = "app/data/historical.xlsx",
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    End-to-end analysis:
      - Load OHLCV from Excel/ccxt
      - Run scenarios analyzer
      - Attach TP/SL rules
      - Return payload ready for delivery
    """
    try:
        df: pd.DataFrame = get_data(symbol, tf, xlsx_path=xlsx_path)
    except (FileNotFoundError, ValueError) as e:
        return _neutral_payload(symbol, tf, e)

    if df is None or df.empty:
        return _neutral_payload(symbol, tf)

    base_cfg: Dict[str, Any] = {"elliott": {"allow_diagonal": True}}
    merged_cfg: Dict[str, Any] = _merge_dict(base_cfg, cfg or {})

    payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=merged_cfg)

    # Attach last price/time
    last = df.iloc[-1]
    px = float(last.get("close", float("nan")))
    payload["last"] = {
        "timestamp": str(last.get("timestamp", "")),
        "close": px,
        "high": float(last.get("high", float("nan"))),
        "low": float(last.get("low", float("nan"))),
        "volume": float(last.get("volume", float("nan"))),
    }

    # เพิ่ม TP/SL rule
    tp_levels = [0.03, 0.05, 0.07]
    sl_level = 0.03
    if not math.isnan(px):
        payload["risk"] = {
            "entry": px,
            "tp": [px * (1 + t) for t in tp_levels],
            "sl": px * (1 - sl_level),
            "tp_pct": tp_levels,
            "sl_pct": sl_level,
        }

    payload["symbol"] = symbol
    payload["tf"] = tf
    return payload


def build_brief_message(payload: Dict[str, Any]) -> str:
    """
    Create a short summary suitable for LINE messages.
    Safe even if fields are missing.
    """
    sym = payload.get("symbol", "")
    tf = payload.get("tf", "")
    pct = payload.get("percent", {}) or {}
    up, down, side = pct.get("up","?"), pct.get("down","?"), pct.get("side","?")

    levels = payload.get("levels", {}) or {}
    rh, rl = levels.get("recent_high"), levels.get("recent_low")
    ema50, ema200 = levels.get("ema50"), levels.get("ema200")

    last = payload.get("last", {}) or {}
    px = last.get("close")

    risk = payload.get("risk", {}) or {}
    tp_pct = risk.get("tp_pct", [0.03, 0.05, 0.07])
    sl_pct = risk.get("sl_pct", 0.03)

    lines: list[str] = []
    lines.append(f"{sym} ({tf})")
    if isinstance(px,(int,float)) and not math.isnan(px):
        lines.append(f"ราคา: {px:,.2f}")
    lines.append(f"ความน่าจะเป็น — ขึ้น {up}% | ลง {down}% | ออกข้าง {side}%")

    if isinstance(rh,(int,float)) and isinstance(rl,(int,float)) and not (math.isnan(rh) or math.isnan(rl)):
        lines.append(f"กรอบล่าสุด: H {rh:,.2f} / L {rl:,.2f}")
    if isinstance(ema50,(int,float)) and isinstance(ema200,(int,float)) and not (math.isnan(ema50) or math.isnan(ema200)):
        lines.append(f"EMA50 {ema50:,.2f} / EMA200 {ema200:,.2f}")

    # ✅ เพิ่ม TP/SL rule ในข้อความ
    if isinstance(px,(int,float)) and not math.isnan(px):
        tp_txt = " / ".join([f"{int(t*100)}%" for t in tp_pct])
        lines.append(f"TP: {tp_txt} | SL: {int(sl_pct*100)}%")

    rationale = payload.get("rationale", []) or []
    if rationale:
        lines.append("เหตุผลย่อ:")
        for r in rationale[:3]:
            lines.append(f"• {r}")

    return "\n".join(lines)
