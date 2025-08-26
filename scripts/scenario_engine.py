import json, math
from typing import Dict
from app.analysis.timeframes import get_data
from app.analysis.indicators import apply_indicators
from app.analysis.dow import analyze_dow
from app.analysis import elliott as ew

SYMBOL = "BTCUSDT"

def last_vals(df, keys):
    row = df.iloc[-1]
    out={}
    for k in keys:
        if k in df.columns:
            v=row[k]
            out[k]=None if v!=v else float(v) if hasattr(v,"__float__") else v
    return out

def score_from_indicators(ind: Dict[str, float], tf: str):
    """ให้คะแนน +bull / +bear / +side จาก EMA/RSI/MACD/Stoch แบบ heuristic เบาๆ"""
    bull = bear = side = 0.0
    c = ind.get("close")
    ema20, ema50, ema200 = ind.get("ema20"), ind.get("ema50"), ind.get("ema200")
    rsi = ind.get("rsi14"); macd = ind.get("macd"); macd_sig = ind.get("macd_signal"); macd_hist = ind.get("macd_hist")
    k, d = ind.get("stoch_k"), ind.get("stoch_d")

    # Trend structure (น้ำหนักสูงใน 4H)
    w = 1.0 if tf=="1H" else 1.7
    if all(x is not None for x in (ema20,ema50,ema200)):
        if ema20>ema50>ema200: bull += 2.5*w
        elif ema20<ema50<ema200: bear += 2.5*w
        else: side += 1.0*w

    # RSI
    if rsi is not None:
        if rsi>=55: bull += 1.0*w
        elif rsi<=45: bear += 1.0*w
        else: side += 0.5*w

    # MACD
    if macd is not None and macd_sig is not None and macd_hist is not None:
        if macd>macd_sig and macd_hist>0: bull += 1.2*w
        elif macd<macd_sig and macd_hist<0: bear += 1.2*w
        else: side += 0.6*w

    # Stochastic (สั้น/โซน)
    if k is not None and d is not None:
        if k>60 and d>60 and k>=d: bull += 0.6*w
        elif k<40 and d<40 and k<=d: bear += 0.6*w
        else: side += 0.3*w

    return bull, bear, side

def score_from_dow(dow: Dict, tf: str):
    bull=bear=side=0.0
    w = 0.9 if tf=="1H" else 1.4
    trend = (dow or {}).get("trend_primary") or (dow or {}).get("trend")
    if trend=="UP": bull += 2.0*w
    elif trend=="DOWN": bear += 2.0*w
    else: side += 1.0*w
    # rule details (HH/HL vs LH/LL)
    rules = (dow or {}).get("rules") or []
    for r in rules:
        nm = r.get("name","")
        ok = bool(r.get("passed", False))
        if nm.startswith("Higher") and ok: bull += 0.4*w
        if nm.startswith("Lower") and ok: bear += 0.4*w
    return bull,bear,side

def score_from_elliott(ell: Dict):
    bull=bear=side=0.0
    w = 1.2
    pat = (ell or {}).get("pattern","").upper()
    # เบาๆ: IMPULSE + direction จาก swings ล่าสุด (approx)
    if pat=="IMPULSE":
        # ถ้า LL ล่าสุดต่ำลง → bias ลง, ถ้า HH สูงขึ้น → bias ขึ้น
        debug = (ell or {}).get("debug",{})
        prices = debug.get("window_prices") or []
        types = debug.get("window_types") or []
        if len(prices)>=2 and len(types)>=2:
            last_p, prev_p = prices[-1], prices[-2]
            last_t, prev_t = types[-1], types[-2]
            if last_t=="L" and prev_t=="H" and last_p<prev_p: bear += 1.5*w
            elif last_t=="H" and prev_t=="L" and last_p>prev_p: bull += 1.5*w
        else:
            side += 0.8*w
    elif pat in ("ZIGZAG","FLAT","TRIANGLE"):
        side += 1.5*w
    else:
        side += 0.8*w
    return bull,bear,side

def normalize_to_pct(bull,bear,side):
    s = max(1e-6, bull+bear+side)
    return {
        "UP_pct": round(100*bull/s,2),
        "DOWN_pct": round(100*bear/s,2),
        "SIDE_pct": round(100*side/s,2),
        "score_raw": {"bull": round(bull,3), "bear": round(bear,3), "side": round(side,3)}
    }

def main():
    # 1) 1H
    df1 = get_data(SYMBOL, "1H"); 
    if df1 is None or df1.empty: raise SystemExit("❌ 1H empty")
    dfi1 = apply_indicators(df1.copy())
    ind1 = last_vals(dfi1, ["timestamp","close","ema20","ema50","ema200","rsi14","macd","macd_signal","macd_hist","stoch_k","stoch_d"])
    dow1 = {}
    try: dow1 = analyze_dow(dfi1.copy())
    except Exception as e: dow1={"error":str(e)}

    # 2) 4H
    df4 = get_data(SYMBOL, "4H");
    if df4 is None or df4.empty: raise SystemExit("❌ 4H empty")
    dfi4 = apply_indicators(df4.copy())
    ind4 = last_vals(dfi4, ["timestamp","close","ema20","ema50","ema200","rsi14","macd","macd_signal","macd_hist","stoch_k","stoch_d"])
    dow4 = {}
    try: dow4 = analyze_dow(dfi4.copy())
    except Exception as e: dow4={"error":str(e)}

    # 3) Elliott จาก 4H
    ell = {}
    try:
        e = ew.analyze_elliott(dfi4.copy())
        ell = e if isinstance(e, dict) else {"result": str(e)}
    except Exception as e:
        ell={"error":str(e)}

    # ---- คะแนนรวม ----
    b1,br1,sd1 = score_from_indicators(ind1,"1H")
    b4,br4,sd4 = score_from_indicators(ind4,"4H")
    db1,dr1,ds1 = score_from_dow(dow1,"1H")
    db4,dr4,ds4 = score_from_dow(dow4,"4H")
    be,bre,sde  = score_from_elliott(ell)

    bull = b1+b4+db1+db4+be
    bear = br1+br4+dr1+dr4+bre
    side = sd1+sd4+ds1+ds4+sde

    pct = normalize_to_pct(bull,bear,side)

    # เหตุผลย่อ
    reasons = []
    if ind4.get("ema20") and ind4.get("ema50") and ind4.get("ema200"):
        if ind4["ema20"]<ind4["ema50"]<ind4["ema200"]:
            reasons.append("4H: EMA20<EMA50<EMA200 (downtrend)")
        elif ind4["ema20"]>ind4["ema50"]>ind4["ema200"]:
            reasons.append("4H: EMA20>EMA50>EMA200 (uptrend)")
    if ind4.get("rsi14") is not None:
        if ind4["rsi14"]<45: reasons.append("4H: RSI < 45 (weak momentum)")
        elif ind4["rsi14"]>55: reasons.append("4H: RSI > 55 (strong momentum)")
    tr4 = (dow4 or {}).get("trend_primary") or (dow4 or {}).get("trend")
    if tr4: reasons.append(f"4H Dow: {tr4}")
    if (ell or {}).get("pattern"): reasons.append(f"Elliott: {ell.get('pattern')}")

    out = {
        "symbol": SYMBOL,
        "last_1H": ind1,
        "last_4H": ind4,
        "dow_1H": dow1,
        "dow_4H": dow4,
        "elliott_4H": ell,
        "scenario": pct | {"reasons": reasons}
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

if __name__ == "__main__":
    main()
