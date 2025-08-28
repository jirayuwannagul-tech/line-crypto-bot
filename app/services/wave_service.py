# app/services/wave_service.py
# -----------------------------------------------------------------------------
# Orchestrator for wave analysis pipeline.
# Load data -> compute scenarios (Dow + Elliott + Fibo + Indicators) -> payload.
# + Elliott RULES + FRACTAL bundle (data-driven) merged in.
# -----------------------------------------------------------------------------
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional, Any, List
import pandas as pd
import math
import json

from app.analysis.timeframes import get_data
# 🔧 logic layer
from app.logic.scenarios import analyze_scenarios
from app.logic.elliott_logic import classify_elliott_with_kind
# 🔌 live data (ccxt/binance) — safe wrapper
from app.adapters.price_provider import get_ohlcv_ccxt_safe

# ✅ data-driven Elliott (rules + fractal)
from app.analysis.elliott_rules import analyze_elliott_rules_v2
from app.analysis.elliott_fractal import analyze_elliott_fractal

__all__ = [
    "analyze_wave",
    "build_brief_message",
    "analyze_df_elliott",
    "analyze_elliott_bundle",
    "WaveAnalyzeOptions",
]

# -----------------------------------------------------------------------------
# Helpers (generic)
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
# Elliott bundle (RULES + FRACTAL) — data-driven layer
# -----------------------------------------------------------------------------
@dataclass
class WaveAnalyzeOptions:
    schema_path: Optional[str] = None
    # rules layer
    pivot_left: Optional[int] = None
    pivot_right: Optional[int] = None
    max_swings: Optional[int] = None
    # fractal layer
    enable_fractal: bool = True
    degree: str = "Minute"
    sub_pivot_left: int = 2
    sub_pivot_right: int = 2


def analyze_elliott_bundle(df: pd.DataFrame, opts: Optional[WaveAnalyzeOptions] = None) -> Dict[str, Any]:
    """
    รวมผล RULES + (เลือกได้) FRACTAL เป็นแพ็กเดียวสำหรับใช้ใน LINE bot / engine
    ไม่ทำ IO ใด ๆ — รับ df พร้อมคอลัมน์ high/low/close เท่านั้น
    """
    opts = opts or WaveAnalyzeOptions()

    # 1) RULES
    rules_res = analyze_elliott_rules_v2(
        df,
        schema_path=opts.schema_path,
        pivot_left=opts.pivot_left,
        pivot_right=opts.pivot_right,
        max_swings=opts.max_swings,
    )

    # 2) FRACTAL (ต่อยอดจากหน้าต่างเดียวกัน)
    if opts.enable_fractal:
        fractal_res = analyze_elliott_fractal(
            df,
            schema_path=opts.schema_path,
            degree=opts.degree,
            sub_pivot_left=opts.sub_pivot_left,
            sub_pivot_right=opts.sub_pivot_right,
        )
    else:
        fractal_res = {**rules_res, "fractal": {"checked": False, "reason": "disabled"}}

    # 3) รวมผล
    bundle: Dict[str, Any] = {
        "pattern": fractal_res.get("pattern", rules_res.get("pattern", "UNKNOWN")),
        "variant": fractal_res.get("variant", rules_res.get("variant", "")),
        "wave_label": fractal_res.get("wave_label", rules_res.get("wave_label", "UNKNOWN")),
        "rules": rules_res.get("rules", []),
        "fractal": fractal_res.get("fractal", {"checked": False}),
        "degree": fractal_res.get("degree", opts.degree),
        "targets": rules_res.get("targets", {}),
        "completed": bool(rules_res.get("completed", False) and fractal_res.get("fractal", {}).get("passed_all_subwaves", False)),
        "debug": {
            "rules_debug": rules_res.get("debug", {}),
            "fractal_debug": fractal_res.get("debug", {}),
        },
        "meta": {
            "options": asdict(opts),
            "schema_used": opts.schema_path or "default",
        },
    }
    return bundle


def analyze_df_elliott(df: pd.DataFrame, **kwargs) -> Dict[str, Any]:
    """proxy แบบ keyword-friendly"""
    opts = WaveAnalyzeOptions(**kwargs)
    return analyze_elliott_bundle(df, opts)


# -----------------------------------------------------------------------------
# Public API (orchestrator)
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
      - แนบ Elliott (RULES + FRACTAL bundle)
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
    weekly_bias: Optional[str] = None
    try:
        if cfg.get("use_live"):
            wdf = get_ohlcv_ccxt_safe(_to_pair(symbol), "1W", int(cfg.get("live_limit", 500)))
        else:
            wdf = get_data(symbol, "1W", xlsx_path=xlsx_path)
        if wdf is not None and not wdf.empty:
            weekly_ctx = classify_elliott_with_kind(wdf, timeframe="1W")
            weekly_bias = ((weekly_ctx or {}).get("current") or {}).get("weekly_bias") \
                          or ((weekly_ctx or {}).get("current") or {}).get("direction")
    except Exception:
        weekly_ctx = None  # fail-safe

    # 4) Run scenarios (รองรับ weekly_ctx ถ้ามี)
    try:
        payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=merged_cfg, weekly_ctx=weekly_ctx)
    except TypeError:
        payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=merged_cfg)

    # 4.1) แนบ Elliott (RULES + FRACTAL bundle) ลง levels.elliott
    try:
        ell_opts = (merged_cfg.get("elliott_opts") or {})
        ell_res = analyze_df_elliott(
            df,
            **{
                "schema_path": ell_opts.get("schema_path"),
                "pivot_left": ell_opts.get("pivot_left"),
                "pivot_right": ell_opts.get("pivot_right"),
                "max_swings": ell_opts.get("max_swings"),
                "enable_fractal": ell_opts.get("enable_fractal", True),
                "degree": ell_opts.get("degree", "Minute"),
                "sub_pivot_left": ell_opts.get("sub_pivot_left", 2),
                "sub_pivot_right": ell_opts.get("sub_pivot_right", 2),
            },
        )
        levels = payload.setdefault("levels", {})
        levels["elliott"] = {
            "pattern": ell_res.get("pattern", "UNKNOWN"),
            "variant": ell_res.get("variant", ""),
            "wave_label": ell_res.get("wave_label", "UNKNOWN"),
            "rules": ell_res.get("rules", []),
            "fractal": ell_res.get("fractal", {}),
            "degree": ell_res.get("degree"),
            "completed": ell_res.get("completed", False),
            "debug": ell_res.get("debug", {}),
        }
    except Exception as _e:
        payload.setdefault("rationale", []).append(f"Elliott (bundle) failed: {_e!s}")

    # 5) Attach last price/time
    last = df.iloc[-1]
    px = float(last.get("close", float("nan")))
    payload["last"] = {
        "timestamp": str(last.get("timestamp", "")),
        "close": px,
        "high": float(last.get("high", float("nan"))),
        "low": float(last.get("low", float("nan"))),
        "volume": float(last.get("volume", float("nan"))),
    }

    # 6) Attach TP/SL rule
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

    # 8) Surface weekly bias (ถ้ามี) ลง levels.elliott.current.weekly_bias
    try:
        if weekly_bias:
            lv = payload.setdefault("levels", {})
            ell = lv.setdefault("elliott", {})
            cur = ell.setdefault("current", {})
            cur["weekly_bias"] = weekly_bias
    except Exception:
        pass

    return payload


def build_brief_message(payload: Dict[str, Any]) -> str:
    """
    แปลง payload -> ข้อความสั้นส่ง LINE
    - รองรับ weekly bias: แสดงเป็นแท็กในบรรทัดแรก เช่น "[UP 1W]"
    - ถ้า payload เป็นรูปแบบ scenario เดิม/ใหม่ จะยังคงทำงานได้ปลอดภัย
    """
    sym = payload.get("symbol") or payload.get("meta", {}).get("symbol") or "SYMBOL"
    tf = payload.get("tf") or payload.get("meta", {}).get("tf") or ""
    pct = payload.get("percent") or {}
    up = pct.get("up") or pct.get("UP_pct")
    down = pct.get("down") or pct.get("DOWN_pct")
    side = pct.get("side") or pct.get("SIDE_pct")

    # weekly bias (จาก levels.elliott.current.weekly_bias หรือ meta.weekly_bias)
    weekly_bias = None
    try:
        weekly_bias = (
            (((payload.get("levels") or {}).get("elliott") or {}).get("current") or {}).get("weekly_bias")
            or (payload.get("meta") or {}).get("weekly_bias")
        )
    except Exception:
        weekly_bias = None

    tag = ""
    if isinstance(weekly_bias, str) and weekly_bias:
        w = weekly_bias.strip().lower()
        norm = "SIDE" if w.startswith("side") else w.upper()
        tag = f" [{norm} 1W]"

    header = f"[{sym}] Scenario{tag}"
    lines: List[str] = [header]

    # ราคา/สถิติ
    last = payload.get("last") or {}
    px = last.get("close")
    px_txt = _fmt_num(px)
    if px_txt:
        lines.append(f"ราคา: {px_txt}")

    if isinstance(up, (int, float)) or isinstance(down, (int, float)) or isinstance(side, (int, float)):
        def _pf(v):
            if v is None: return "?"
            try:
                return f"{float(v):.0f}%"
            except Exception:
                return "?"
        lines.append(f"ความน่าจะเป็น — ขึ้น {_pf(up)} | ลง {_pf(down)} | ออกข้าง {_pf(side)}")

    # กรอบ/EMA
    levels = payload.get("levels") or {}
    rh, rl = levels.get("recent_high"), levels.get("recent_low")
    ema50, ema200 = levels.get("ema50"), levels.get("ema200")
    rh_txt, rl_txt = _fmt_num(rh), _fmt_num(rl)
    if rh_txt and rl_txt:
        lines.append(f"กรอบล่าสุด: H {rh_txt} / L {rl_txt}")
    ema50_txt, ema200_txt = _fmt_num(ema50), _fmt_num(ema200)
    if ema50_txt and ema200_txt:
        lines.append(f"EMA50 {ema50_txt} / EMA200 {ema200_txt}")

    # TP/SL
    risk = payload.get("risk") or {}
    tp_pct: List[float] = risk.get("tp_pct", [0.03, 0.05, 0.07])
    sl_pct: float = risk.get("sl_pct", 0.03)
    tp_txt = " / ".join([f"{int(t * 100)}%" for t in tp_pct])
    lines.append(f"TP: {tp_txt} | SL: {int(sl_pct * 100)}%")

    # เหตุผลย่อ
    rationale = payload.get("rationale") or []
    if rationale:
        lines.append("เหตุผลย่อ:")
        for r in rationale[:3]:
            lines.append(f"• {r}")

    return "\n".join(lines)
