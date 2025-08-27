# -----------------------------------------------------------------------------
# Orchestrator for wave analysis pipeline.
# Load data -> compute scenarios (Dow + Elliott + Fibo + Indicators) -> payload.
# -----------------------------------------------------------------------------
from __future__ import annotations

from typing import Dict, Optional, Any, List
import pandas as pd
import math

from app.analysis.timeframes import get_data
# 🔧 logic layer
from app.logic.scenarios import analyze_scenarios
from app.logic.elliott_logic import classify_elliott_with_kind
# �� live data (ccxt/binance) — safe wrapper
from app.adapters.price_provider import get_ohlcv_ccxt_safe


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


def _fmt_num(v: Optional[float]) -> Optional[str]:
    if isinstance(v, (int, float)) and not math.isnan(v):
        return f"{v:,.2f}"
    return None


def _to_pair(symbol: str) -> str:
    """
    สร้างรูปแบบคู่เทรดสำหรับ live data:
    - ถ้า symbol มี "/" อยู่แล้ว → คืนเดิม
    - ถ้าเป็น BTCUSDT → แปลงเป็น BTC/USDT
    - อื่น ๆ → ผูกกับ USDT โดยอัตโนมัติ เช่น BTC → BTC/USDT
    """
    s = (symbol or "").strip().upper()
    if "/" in s:
        return s
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}/USDT"
    return f"{s}/USDT"


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
      - หาก cfg['use_live'] เป็น True: โหลด OHLCV จาก Binance (ผ่าน price_provider)
      - ไม่เช่นนั้น: โหลดจาก Excel/CSV (ผ่าน timeframes.get_data)
      - Run scenarios (+ optional Weekly context)
      - แนบ TP/SL (3%,5%,7% / SL 3%) และ metadata พื้นฐาน
    """
    cfg = cfg or {}

    # 1) Load main TF data (live หรือ file)
    try:
        if cfg.get("use_live"):
            limit = int(cfg.get("live_limit", 500))
            pair = _to_pair(symbol)
            df: pd.DataFrame = get_ohlcv_ccxt_safe(pair, tf, limit)
            if df is None or df.empty:
                return _neutral_payload(symbol, tf, err=RuntimeError("no live OHLCV"))
        else:
            df: pd.DataFrame = get_data(symbol, tf, xlsx_path=xlsx_path)
            if df is None or df.empty:
                return _neutral_payload(symbol, tf)
    except Exception as e:
        return _neutral_payload(symbol, tf, e)

    # 2) Merge config (safe defaults)
    base_cfg: Dict[str, Any] = {"elliott": {"allow_diagonal": True}}
    merged_cfg: Dict[str, Any] = _merge_dict(base_cfg, cfg or {})

    # 3) Weekly context (1W) — best effort
    weekly_ctx: Optional[Dict[str, Any]] = None
    try:
        if cfg.get("use_live"):
            wdf = get_ohlcv_ccxt_safe(_to_pair(symbol), "1W", int(cfg.get("live_limit", 500)))
        else:
            wdf = get_data(symbol, "1W", xlsx_path=xlsx_path)
        if wdf is not None and not wdf.empty:
            weekly_ctx = classify_elliott_with_kind(wdf, timeframe="1W")
    except Exception:
        weekly_ctx = None  # fail-safe

    # 4) Run scenarios (รองรับ weekly_ctx ถ้ามี)
    try:
        payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=merged_cfg, weekly_ctx=weekly_ctx)
    except TypeError:
        payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=merged_cfg)

    # 5) Attach last price/time (surface สำหรับ LINE text)
    last = df.iloc[-1]
    px = float(last.get("close", float("nan")))
    payload["last"] = {
        "timestamp": str(last.get("timestamp", "")),
        "close": px,
        "high": float(last.get("high", float("nan"))),
        "low": float(last.get("low", float("nan"))),
        "volume": float(last.get("volume", float("nan"))),
    }

    # 6) Attach TP/SL rule (surface)
    tp_levels = [0.03, 0.05, 0.07]
    sl_level = 0.03
    if isinstance(px, (int, float)) and not math.isnan(px):
        payload["risk"] = {
            "entry": px,
            "tp": [px * (1 + t) for t in tp_levels],
            "sl": px * (1 - sl_level),
            "tp_pct": tp_levels,
            "sl_pct": sl_level,
        }

    # 7) Ensure meta fields
    payload["symbol"] = symbol
    payload["tf"] = tf

    # 8) Surface weekly bias (ถ้ามี)
    try:
        if weekly_ctx:
            lv = payload.setdefault("levels", {})
            ell = lv.setdefault("elliott", {})
            cur = ell.setdefault("current", {})
            if "weekly_bias" not in cur and isinstance(weekly_ctx, dict):
                wb = (weekly_ctx.get("current") or {}).get("weekly_bias")
                if wb:
                    cur["weekly_bias"] = wb
    except Exception:
        pass

    return payload


def build_brief_message(payload: Dict[str, Any]) -> str:
    """
    Create a short summary suitable for LINE messages.
    Also prints trading plans (A/B/C) at the end for terminal usage.
    Safe even if fields are missing.
    """
    sym = payload.get("symbol", "")
    tf = payload.get("tf", "")
    pct = payload.get("percent", {}) or {}
    up, down, side = pct.get("up", "?"), pct.get("down", "?"), pct.get("side", "?")

    levels = payload.get("levels", {}) or {}
    rh, rl = levels.get("recent_high"), levels.get("recent_low")
    ema50, ema200 = levels.get("ema50"), levels.get("ema200")

    last = payload.get("last", {}) or {}
    px = last.get("close")

    risk = payload.get("risk", {}) or {}
    tp_pct: List[float] = risk.get("tp_pct", [0.03, 0.05, 0.07])
    sl_pct: float = risk.get("sl_pct", 0.03)

    # Optional weekly bias line
    weekly_line = ""
    wb_for_plan = "?"
    try:
        ell = levels.get("elliott") or {}
        cur = ell.get("current") or {}
        wb = cur.get("weekly_bias")
        if isinstance(wb, str) and wb:
            weekly_line = f" [{wb.upper()} 1W]"
            wb_for_plan = wb.upper()
    except Exception:
        pass

    def _fmt_num(v: Optional[float]) -> Optional[str]:
        if isinstance(v, (int, float)) and not math.isnan(v):
            return f"{v:,.2f}"
        return None

    lines: List[str] = []
    header = f"{sym} ({tf}){weekly_line}"
    lines.append(header)

    px_txt = _fmt_num(px)
    if px_txt:
        lines.append(f"ราคา: {px_txt}")

    lines.append(f"ความน่าจะเป็น — ขึ้น {up}% | ลง {down}% | ออกข้าง {side}%")

    rh_txt, rl_txt = _fmt_num(rh), _fmt_num(rl)
    if rh_txt and rl_txt:
        lines.append(f"กรอบล่าสุด: H {rh_txt} / L {rl_txt}")

    ema50_txt, ema200_txt = _fmt_num(ema50), _fmt_num(ema200)
    if ema50_txt and ema200_txt:
        lines.append(f"EMA50 {ema50_txt} / EMA200 {ema200_txt}")

    tp_txt = " / ".join([f"{int(t * 100)}%" for t in tp_pct])
    lines.append(f"TP: {tp_txt} | SL: {int(sl_pct * 100)}%")

    rationale = payload.get("rationale", []) or []
    if rationale:
        lines.append("เหตุผลย่อ:")
        for r in rationale[:3]:
            lines.append(f"• {r}")

    # === Trading Plans block (terminal-friendly) ===
    try:
        px_val = float(px) if isinstance(px, (int, float)) else float("nan")
        rh_val = float(rh) if isinstance(rh, (int, float)) else None
        rl_val = float(rl) if isinstance(rl, (int, float)) else None
        ema50_val = float(ema50) if isinstance(ema50, (int, float)) else None

        lines.append("")
        lines.append(f"แผนเทรดที่แนะนำตอนนี้ (Weekly = {wb_for_plan}, 1D bias ขึ้น/ลง/ข้าง = {up}%/{down}%/{side}%)")

        # A) Short – Breakout
        if rl_val and rl_val > 0:
            entry = rl_val
            lines.append("")
            lines.append("A) Short – Breakout (ปลอดภัยกว่า)")
            lines.append(f"Entry: หลุด {entry:,.2f}")
            tp1, tp2, tp3 = entry * 0.97, entry * 0.95, entry * 0.93
            sl = entry * 1.03
            lines.append(f"TP1 −3%: {tp1:,.2f} | TP2 −5%: {tp2:,.2f} | TP3 −7%: {tp3:,.2f}")
            lines.append(f"SL +3%: {sl:,.2f}")

        # B) Short – Pullback
        if ema50_val and ema50_val > 0:
            entry = ema50_val
            lines.append("")
            lines.append("B) Short – Pullback (เชิงรุก/RR ดีกว่า)")
            lines.append(f"Entry: รีเจ็กต์แถว EMA50 = {entry:,.2f}")
            tp1, tp2, tp3 = entry * 0.97, entry * 0.95, entry * 0.93
            sl = entry * 1.03
            lines.append(f"TP1 −3%: {tp1:,.2f} | TP2 −5%: {tp2:,.2f} | TP3 −7%: {tp3:,.2f}")
            lines.append(f"SL +3%: {sl:,.2f}")

        # C) Long – แผนสำรอง
        if rh_val and rh_val > 0:
            entry = rh_val
            lines.append("")
            lines.append("C) Long – แผนสำรอง (ถ้ากลับตัวแรง)")
            lines.append(f"Entry: ทะลุ Recent High = {entry:,.2f}")
            tp1, tp2, tp3 = entry * 1.03, entry * 1.05, entry * 1.07
            sl = entry * 0.97
            lines.append(f"TP1 +3%: {tp1:,.2f} | TP2 +5%: {tp2:,.2f} | TP3 +7%: {tp3:,.2f}")
            lines.append(f"SL −3%: {sl:,.2f}")
    except Exception:
        pass

    return "\n".join(lines)
