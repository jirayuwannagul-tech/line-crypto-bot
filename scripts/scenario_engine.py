# [ไฟล์] scripts/scenario_engine.py  (แทนที่ทั้งไฟล์)
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

from app.analysis.timeframes import get_data
from app.analysis.indicators import apply_indicators
from app.analysis.dow import analyze_dow
from app.analysis import elliott as ew


# -------------------------------
# Utilities
# -------------------------------
def last_vals(df, keys):
    row = df.iloc[-1]
    out = {}
    for k in keys:
        if k in df.columns:
            v = row[k]
            out[k] = None if v != v else float(v) if hasattr(v, "__float__") else v  # NaN-safe
    return out


def score_from_indicators(ind: Dict[str, float], tf: str) -> Tuple[float, float, float]:
    """ให้คะแนน +bull / +bear / +side จาก EMA/RSI/MACD/Stoch แบบ heuristic เบาๆ"""
    bull = bear = side = 0.0
    ema20, ema50, ema200 = ind.get("ema20"), ind.get("ema50"), ind.get("ema200")
    rsi = ind.get("rsi14")
    macd = ind.get("macd")
    macd_sig = ind.get("macd_signal")
    macd_hist = ind.get("macd_hist")
    k, d = ind.get("stoch_k"), ind.get("stoch_d")

    # Weight: 1D > 4H > 1H
    w = {"1H": 1.0, "4H": 1.7, "1D": 2.2}.get(tf, 1.0)
    if all(x is not None for x in (ema20, ema50, ema200)):
        if ema20 > ema50 > ema200:
            bull += 2.5 * w
        elif ema20 < ema50 < ema200:
            bear += 2.5 * w
        else:
            side += 1.0 * w

    if rsi is not None:
        if rsi >= 55:
            bull += 1.0 * w
        elif rsi <= 45:
            bear += 1.0 * w
        else:
            side += 0.5 * w

    if macd is not None and macd_sig is not None and macd_hist is not None:
        if macd > macd_sig and macd_hist > 0:
            bull += 1.2 * w
        elif macd < macd_sig and macd_hist < 0:
            bear += 1.2 * w
        else:
            side += 0.6 * w

    if k is not None and d is not None:
        if k > 60 and d > 60 and k >= d:
            bull += 0.6 * w
        elif k < 40 and d < 40 and k <= d:
            bear += 0.6 * w
        else:
            side += 0.3 * w

    return bull, bear, side


def score_from_dow(dow: Dict, tf: str) -> Tuple[float, float, float]:
    bull = bear = side = 0.0
    w = {"1H": 0.9, "4H": 1.4, "1D": 1.8}.get(tf, 1.0)
    trend = (dow or {}).get("trend_primary") or (dow or {}).get("trend")
    if trend == "UP":
        bull += 2.0 * w
    elif trend == "DOWN":
        bear += 2.0 * w
    else:
        side += 1.0 * w

    for r in (dow or {}).get("rules") or []:
        nm = r.get("name", "")
        ok = bool(r.get("passed", False))
        if nm.startswith("Higher") and ok:
            bull += 0.4 * w
        if nm.startswith("Lower") and ok:
            bear += 0.4 * w
    return bull, bear, side


def score_from_elliott(ell: Dict) -> Tuple[float, float, float]:
    bull = bear = side = 0.0
    w = 1.2
    pat = (ell or {}).get("pattern", "").upper()
    if pat == "IMPULSE":
        debug = (ell or {}).get("debug", {})
        prices = debug.get("window_prices") or []
        types = debug.get("window_types") or []
        if len(prices) >= 2 and len(types) >= 2:
            last_p, prev_p = prices[-1], prices[-2]
            last_t, prev_t = types[-1], types[-2]
            if last_t == "L" and prev_t == "H" and last_p < prev_p:
                bear += 1.5 * w
            elif last_t == "H" and prev_t == "L" and last_p > prev_p:
                bull += 1.5 * w
        else:
            side += 0.8 * w
    elif pat in ("ZIGZAG", "FLAT", "TRIANGLE"):
        side += 1.5 * w
    else:
        side += 0.8 * w
    return bull, bear, side


def normalize_to_pct(bull: float, bear: float, side: float) -> Dict[str, float]:
    s = max(1e-6, bull + bear + side)
    return {
        "UP_pct": round(100 * bull / s, 2),
        "DOWN_pct": round(100 * bear / s, 2),
        "SIDE_pct": round(100 * side / s, 2),
        "score_raw": {"bull": round(bull, 3), "bear": round(bear, 3), "side": round(side, 3)},
    }


def _safe_get_data(symbol: str, tf: str, rows: int | None):
    """พยายามส่ง rows ให้ get_data ถ้าซิกเนเจอร์รองรับ ไม่งั้น tail ภายหลัง"""
    try:
        df = get_data(symbol, tf, rows=rows)  # type: ignore[arg-type]
    except TypeError:
        df = get_data(symbol, tf)
        if rows:
            df = df.tail(rows)
    return df


def build_output(symbol: str, rows: int | None) -> Dict:
    # 1) 1H
    df1 = _safe_get_data(symbol, "1H", rows)
    if df1 is None or df1.empty:
        raise SystemExit("❌ 1H empty")
    dfi1 = apply_indicators(df1.copy())
    ind1 = last_vals(
        dfi1, ["timestamp", "close", "ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist", "stoch_k", "stoch_d"]
    )
    try:
        dow1 = analyze_dow(dfi1.copy())
    except Exception as e:
        dow1 = {"error": str(e)}

    # 2) 4H
    df4 = _safe_get_data(symbol, "4H", rows)
    if df4 is None or df4.empty:
        raise SystemExit("❌ 4H empty")
    dfi4 = apply_indicators(df4.copy())
    ind4 = last_vals(
        dfi4, ["timestamp", "close", "ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist", "stoch_k", "stoch_d"]
    )
    try:
        dow4 = analyze_dow(dfi4.copy())
    except Exception as e:
        dow4 = {"error": str(e)}

    # 3) 1D
    dfD = _safe_get_data(symbol, "1D", rows)
    if dfD is None or dfD.empty:
        raise SystemExit("❌ 1D empty")
    dfiD = apply_indicators(dfD.copy())
    indD = last_vals(
        dfiD, ["timestamp", "close", "ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist", "stoch_k", "stoch_d"]
    )
    try:
        dowD = analyze_dow(dfiD.copy())
    except Exception as e:
        dowD = {"error": str(e)}

    # 4) Elliott จาก 4H
    try:
        e = ew.analyze_elliott(dfi4.copy())
        ell = e if isinstance(e, dict) else {"result": str(e)}
    except Exception as e:
        ell = {"error": str(e)}

    # ---- คิดคะแนนรวม ----
    b1, br1, sd1 = score_from_indicators(ind1, "1H")
    b4, br4, sd4 = score_from_indicators(ind4, "4H")
    bD, brD, sdD = score_from_indicators(indD, "1D")
    db1, dr1, ds1 = score_from_dow(dow1, "1H")
    db4, dr4, ds4 = score_from_dow(dow4, "4H")
    dbD, drD, dsD = score_from_dow(dowD, "1D")
    be, bre, sde = score_from_elliott(ell)

    bull = b1 + b4 + bD + db1 + db4 + dbD + be
    bear = br1 + br4 + brD + dr1 + dr4 + drD + bre
    side = sd1 + sd4 + sdD + ds1 + ds4 + dsD + sde

    pct = normalize_to_pct(bull, bear, side)

    # เหตุผลย่อ
    reasons = []
    # 4H reasons
    if ind4.get("ema20") and ind4.get("ema50") and ind4.get("ema200"):
        if ind4["ema20"] < ind4["ema50"] < ind4["ema200"]:
            reasons.append("4H: EMA20<EMA50<EMA200 (downtrend)")
        elif ind4["ema20"] > ind4["ema50"] > ind4["ema200"]:
            reasons.append("4H: EMA20>EMA50>EMA200 (uptrend)")
    if ind4.get("rsi14") is not None:
        if ind4["rsi14"] < 45:
            reasons.append("4H: RSI < 45 (weak momentum)")
        elif ind4["rsi14"] > 55:
            reasons.append("4H: RSI > 55 (strong momentum)")
    tr4 = (dow4 or {}).get("trend_primary") or (dow4 or {}).get("trend")
    if tr4:
        reasons.append(f"4H Dow: {tr4}")
    if (ell or {}).get("pattern"):
        reasons.append(f"Elliott: {ell.get('pattern')}")

    # 1D reasons
    if indD.get("ema20") and indD.get("ema50") and indD.get("ema200"):
        if indD["ema20"] < indD["ema50"] < indD["ema200"]:
            reasons.append("1D: EMA20<EMA50<EMA200 (downtrend)")
        elif indD["ema20"] > indD["ema50"] > indD["ema200"]:
            reasons.append("1D: EMA20>EMA50>EMA200 (uptrend)")
    if indD.get("rsi14") is not None:
        if indD["rsi14"] < 45:
            reasons.append("1D: RSI < 45 (weak)")
        elif indD["rsi14"] > 55:
            reasons.append("1D: RSI > 55 (strong)")
    trD = (dowD or {}).get("trend_primary") or (dowD or {}).get("trend")
    if trD:
        reasons.append(f"1D Dow: {trD}")

    out = {
        "symbol": symbol,
        "last_1H": ind1,
        "last_4H": ind4,
        "last_1D": indD,
        "dow_1H": dow1,
        "dow_4H": dow4,
        "dow_1D": dowD,
        "elliott_4H": ell,
        "scenario": pct | {"reasons": reasons},
    }
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scenario Engine (1H/4H/1D blend)")
    p.add_argument("--symbol", default="BTCUSDT", help="เช่น BTCUSDT/ETHUSDT")
    p.add_argument("--rows", type=int, default=600, help="จำกัดจำนวนแถวท้าย (tail)")
    p.add_argument("--out", default=None, help="พาธไฟล์ .json ที่ต้องการบันทึก")
    return p.parse_args()


def main():
    args = parse_args()
    out = build_output(args.symbol, args.rows)

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
