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
    "build_brief_message_for",   # 🆕 wrapper (symbol, tf)
    "analyze_df_elliott",
    "analyze_elliott_bundle",
    "WaveAnalyzeOptions",
]

# -----------------------------------------------------------------------------
# Helpers (generic)
# -----------------------------------------------------------------------------
def _normalize_percent(p):
    u, d, s = float(p.get('up', 0)), float(p.get('down', 0)), float(p.get('side', 0))
    u, d, s = max(0, u), max(0, d), max(0, s)
    tot = u + d + s
    if tot <= 0:
        return {'up': 33, 'down': 33, 'side': 34}
    u = round(100 * u / tot)
    d = round(100 * d / tot)
    s = 100 - u - d
    return {'up': int(u), 'down': int(d), 'side': int(s)}

def _apply_mtf_weight(percent, df30, df15, df5):
    from app.analysis.filters import mtf_filter_stack
    long_res  = mtf_filter_stack(df30, df15, df5, bias="long")
    short_res = mtf_filter_stack(df30, df15, df5, bias="short")

    up, down, side = float(percent['up']), float(percent['down']), float(percent['side'])

    if long_res.get('ready'):
        up += 10
    elif long_res.get('majority'):
        up += 5

    if short_res.get('ready'):
        down += 10
    elif short_res.get('majority'):
        down += 5

    if not long_res.get('majority') and not short_res.get('majority'):
        side += 5

    newp = _normalize_percent({'up': up, 'down': down, 'side': side})
    mtf_meta = {
        'long': {'ready': long_res['ready'], 'majority': long_res['majority'], 'scores': long_res['scores']},
        'short':{'ready': short_res['ready'],'majority': short_res['majority'],'scores': short_res['scores']},
    }
    return newp, mtf_meta

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
    s = (symbol or "").strip().upper()
    if "/" in s:
        return s
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}/USDT"
    return f"{s}/USDT"

def _get_elliott_node(payload: dict) -> dict:
    """
    คืน object Elliott ที่อยู่ใน payload ไม่ว่าจะเก็บไว้ที่
    payload['elliott'] หรือ payload['levels']['elliott']
    """
    if not isinstance(payload, dict):
        return {}
    el = payload.get("elliott")
    if isinstance(el, dict):
        return el
    el2 = (payload.get("levels") or {}).get("elliott")
    if isinstance(el2, dict):
        return el2
    return {}

def _format_elliott_subwaves(payload: dict) -> str:
    """
    ดึง/สรุปคลื่นย่อยจากผล RULES+FRACTAL ภายใน payload:

    - รองรับหลายแหล่ง เช่น ...['fractal']['subwaves'], debug['fractal_debug']['subwaves'], ฯลฯ
    - คืนรูปแบบ: "subwaves: i–ii–iii–iv–v" หรือ "a–b–c"
    """
    try:
        el = _get_elliott_node(payload)
        # candidates ที่น่าจะมี subwaves
        candidates = []
        # 1) ผลรวม bundle
        for k in ("fractal", "rules", "debug"):
            v = el.get(k)
            if isinstance(v, dict):
                candidates.append(v)
        # 2) ลึกลงใน debug
        dbg = el.get("debug", {})
        if isinstance(dbg, dict):
            for k in ("fractal_debug", "rules_debug"):
                if isinstance(dbg.get(k), dict):
                    candidates.append(dbg[k])

        labels: List[str] = []
        # ดึงลิสต์ subwaves จากหลายชื่อคีย์ที่พบได้บ่อย
        for c in candidates:
            for key in ("subwaves", "waves", "children", "items"):
                sv = c.get(key)
                if isinstance(sv, list) and sv:
                    # รองรับทั้ง {"label": "i"} หรือ string ตรง ๆ
                    for w in sv:
                        if isinstance(w, dict) and "label" in w:
                            labels.append(str(w["label"]))
                        elif isinstance(w, str):
                            labels.append(w)
            # บางที่เก็บเป็น dict {"i": {...}, "ii": {...}}
            for key in ("subwaves", "waves"):
                svd = c.get(key)
                if isinstance(svd, dict):
                    labels.extend([str(k) for k in svd.keys()])

        # ทำความสะอาด label เช่น "(i)" -> "i", "W1"->"1"
        import re
        norm: List[str] = []
        for lb in labels:
            t = re.sub(r"[()\s]+", "", lb)
            # แปลงเลขอารบิก 1..5 เป็น i..v ถ้าดูเป็น impulse
            if t in ("1", "2", "3", "4", "5"):
                conv = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v"}[t]
                norm.append(conv)
            else:
                norm.append(t)

        # จัดลำดับฉลาด ๆ: ถ้ามี i..v ครบ ให้เรียง i..v, ถ้ามี a,b,c ก็เรียง a..c
        seq: List[str] = []
        pref_imp = ["i", "ii", "iii", "iv", "v"]
        pref_corr = ["a", "b", "c"]
        has_imp = any(x in norm for x in pref_imp)
        has_corr = any(x in norm for x in pref_corr)
        if has_imp:
            for x in pref_imp:
                if x in norm and x not in seq:
                    seq.append(x)
        if has_corr:
            for x in pref_corr:
                if x in norm and x not in seq:
                    seq.append(x)
        # ถ้ายังว่าง ลอง unique ตามลำดับที่พบ
        if not seq and norm:
            seen = set()
            for x in norm:
                if x not in seen:
                    seen.add(x)
                    seq.append(x)

        if not seq:
            return "subwaves: (ไม่พบข้อมูลคลื่นย่อย)"
        return "subwaves: " + "–".join(seq)
    except Exception:
        return "subwaves: (ไม่พบข้อมูลคลื่นย่อย)"

# -----------------------------------------------------------------------------
# Elliott bundle (RULES + FRACTAL)
# -----------------------------------------------------------------------------
@dataclass
class WaveAnalyzeOptions:
    schema_path: Optional[str] = None
    pivot_left: Optional[int] = None
    pivot_right: Optional[int] = None
    max_swings: Optional[int] = None
    enable_fractal: bool = True
    degree: str = "Minute"
    sub_pivot_left: int = 2
    sub_pivot_right: int = 2

def analyze_elliott_bundle(df: pd.DataFrame, opts: Optional[WaveAnalyzeOptions] = None) -> Dict[str, Any]:
    opts = opts or WaveAnalyzeOptions()
    rules_res = analyze_elliott_rules_v2(
        df,
        schema_path=opts.schema_path,
        pivot_left=opts.pivot_left,
        pivot_right=opts.pivot_right,
        max_swings=opts.max_swings,
    )
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

    return {
        "pattern": fractal_res.get("pattern", rules_res.get("pattern", "UNKNOWN")),
        "variant": fractal_res.get("variant", rules_res.get("variant", "")),
        "wave_label": fractal_res.get("wave_label", rules_res.get("wave_label", "UNKNOWN")),
        "rules": rules_res.get("rules", []),
        "fractal": fractal_res.get("fractal", {"checked": False}),
        "degree": fractal_res.get("degree", opts.degree),
        "targets": rules_res.get("targets", {}),
        "completed": bool(rules_res.get("completed", False) and fractal_res.get("fractal", {}).get("passed_all_subwaves", False)),
        "debug": {"rules_debug": rules_res.get("debug", {}), "fractal_debug": fractal_res.get("debug", {})},
        "meta": {"options": asdict(opts), "schema_used": opts.schema_path or "default"},
    }

def analyze_df_elliott(df: pd.DataFrame, **kwargs) -> Dict[str, Any]:
    opts = WaveAnalyzeOptions(**kwargs)
    return analyze_elliott_bundle(df, opts)

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def analyze_wave(
    symbol: str,
    tf: str = "1D",
    *,
    xlsx_path: Optional[str] = "app/data/historical.xlsx",
    cfg: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    cfg = cfg or {}
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

    base_cfg: Dict[str, Any] = {"elliott": {"allow_diagonal": True}}
    merged_cfg: Dict[str, Any] = _merge_dict(base_cfg, cfg or {})

    weekly_ctx, weekly_bias = None, None
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
        weekly_ctx = None

    try:
        payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=merged_cfg, weekly_ctx=weekly_ctx)
    except TypeError:
        payload = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=merged_cfg)

    # Elliott bundle -> เก็บไว้ใน levels.elliott
    try:
        ell_opts = (merged_cfg.get("elliott_opts") or {})
        ell_res = analyze_df_elliott(df, **ell_opts)
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
            "current": {},  # ไว้แนบ weekly_bias ภายหลัง
        }
    except Exception as _e:
        payload.setdefault("rationale", []).append(f"Elliott (bundle) failed: {_e!s}")

    last = df.iloc[-1]
    px = float(last.get("close", float("nan")))
    payload["last"] = {
        "timestamp": str(last.get("timestamp", "")),
        "close": px,
        "high": float(last.get("high", float("nan"))),
        "low": float(last.get("low", float("nan"))),
        "volume": float(last.get("volume", float("nan"))),
    }

    tp_levels, sl_level = [0.03, 0.05, 0.07], 0.03
    if isinstance(px, (int, float)) and not math.isnan(px):
        payload["risk"] = {
            "entry": px,
            "tp": [px * (1 + t) for t in tp_levels],
            "sl": px * (1 - sl_level),
            "tp_pct": tp_levels,
            "sl_pct": sl_level,
        }

    payload["symbol"] = symbol
    payload["tf"] = tf
    try:
        if weekly_bias:
            lv = payload.setdefault("levels", {})
            ell = lv.setdefault("elliott", {})
            cur = ell.setdefault("current", {})
            cur["weekly_bias"] = weekly_bias
    except Exception:
        pass

    payload.setdefault("meta", {})
    payload["meta"]["mtf"] = (locals().get("mtf_meta") or {"status": "skipped"})
    payload["weekly_ctx"] = weekly_ctx
    return payload

# --- PATCH: improve weekly-bias extraction ---
def _extract_weekly_bias(payload):
    wb = None
    try:
        if isinstance(payload, dict):
            wb = (((payload.get("levels") or {}).get("elliott") or {}).get("current") or {}).get("weekly_bias")
            if not wb:
                wc = payload.get("weekly_ctx") or {}
                cur = wc.get("current") or {}
                wb = cur.get("weekly_bias") or cur.get("direction")
            if not wb:
                wb = payload.get("weekly_bias") or (payload.get("meta", {}) or {}).get("weekly_bias")
    except Exception:
        wb = None
    if isinstance(wb, str):
        wbl = wb.lower()
        if wbl in ("up", "bull", "bullish"):
            return "UP"
        if wbl in ("down", "bear", "bearish"):
            return "DOWN"
    return None
# --- END PATCH ---

def build_brief_message(payload: dict) -> str:
    """
    รับ payload ที่มาจาก analyze_wave(...) แล้วฟอร์แมตเป็นข้อความสั้นสำหรับ LINE/console
    """
    if not isinstance(payload, dict):
        return "?"

    sym = payload.get("symbol") or (payload.get("meta", {}).get("symbol"))
    tf = payload.get("tf") or (payload.get("meta", {}).get("tf"))
    sym = sym or "?"
    tf = tf or "?"

    weekly_bias = _extract_weekly_bias(payload) or "?"
    perc = payload.get("percent", {}) or {}
    p_up = int(perc.get("up", 0))
    p_down = int(perc.get("down", 0))
    p_side = int(perc.get("side", 0))

    last_price = None
    try:
        last_price = float((payload.get("last") or {}).get("close"))
        if math.isnan(last_price):
            last_price = None
    except Exception:
        last_price = None

    lv = payload.get("levels", {}) or {}
    ema50 = lv.get("ema50")
    ema200 = lv.get("ema200")
    high  = lv.get("recent_high")
    low   = lv.get("recent_low")

    lines: List[str] = []
    lines.append(f"{sym} ({tf}) [{weekly_bias} 1W]")
    if last_price is not None:
        lines.append(f"ราคา: {last_price:,.2f}")
    lines.append(f"ความน่าจะเป็น — ขึ้น {p_up}% | ลง {p_down}% | ออกข้าง {p_side}%")
    if high and low:
        lines.append(f"กรอบล่าสุด: H {_fmt_num(high)} / L {_fmt_num(low)}")
    if ema50 and ema200:
        lines.append(f"EMA50 {_fmt_num(ema50)} / EMA200 {_fmt_num(ema200)}")

    # TP/SL (ถ้ามี)
    risk = payload.get("risk") or {}
    if risk.get("tp") and risk.get("sl"):
        try:
            tp_vals = risk["tp"]
            sl_val = risk["sl"]
            # แสดงเป็น % คงที่ตาม risk['tp_pct']/['sl_pct'] หากมี
            tp_pct = risk.get("tp_pct") or []
            sl_pct = risk.get("sl_pct")
            if tp_pct and isinstance(sl_pct, (int, float)):
                # แสดงเป็น +3% / +5% / +7% | SL: -3%
                tp_pct_txt = " / ".join([f"+{int(round(t*100))}%" for t in tp_pct])
                sl_pct_txt = f"-{int(round(sl_pct*100))}%"
                lines.append(f"TP: {tp_pct_txt} | SL: {sl_pct_txt}")
        except Exception:
            pass

    # เหตุผลย่อ (+ Elliott subwaves)
    reasons = payload.get("rationale", [])
    if reasons:
        lines.append("เหตุผลย่อ:")
        for r in reasons:
            lines.append(f"• {r}")

    # เพิ่มหัวข้อ Elliott pattern + subwaves ถ้ามีผลลัพธ์
    el = _get_elliott_node(payload)
    if el:
        try:
            pattern = el.get("pattern") or "Elliott"
            variant = el.get("variant") or ""
            wave_label = el.get("wave_label") or ""
            subwaves_line = _format_elliott_subwaves(payload)
            head = f"• {pattern}"
            if variant:
                head += f" {variant}"
            if wave_label:
                head += f" {wave_label}"
            lines.append(head + f" — {subwaves_line}")
        except Exception:
            pass

    return "\n".join(lines)

# 🆕 wrapper
def build_brief_message_for(symbol: str, tf: str) -> str:
    """
    Wrapper:
    - run analyze_wave(symbol, tf)
    - return build_brief_message(payload)
    """
    payload = analyze_wave(symbol, tf)
    return build_brief_message(payload)
