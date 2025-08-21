# scripts/mta_flow_demo.py
# MTA: 1D→4H→1H พร้อมพิมพ์ PLAN & ALERT สั้นๆ

from app.analysis.timeframes import get_data
from app.analysis.scenarios import analyze_scenarios
from app.analysis.indicators import apply_indicators

SYMBOL = "BTCUSDT"

def _brief(line: str):
    print(f"- {line}")

def main():
    # ---------- 1) 1D: Bias ----------
    df_1d = get_data(SYMBOL, "1D")
    sc_1d = analyze_scenarios(df_1d, symbol=SYMBOL, tf="1D")

    print("\n=== 1) FRAME: 1D (Bias/Context) ===")
    print("percent:", sc_1d["percent"])
    print("levels:", {k: sc_1d["levels"].get(k) for k in ["ema50", "ema200", "recent_high", "recent_low"]})
    _brief("ถ้า 1D = UP → โฟกัส LONG ; ถ้า DOWN → โฟกัส SHORT (หลัก Multi-Timeframe)")

    daily_bias = "up" if sc_1d["percent"]["up"] > max(sc_1d["percent"]["down"], sc_1d["percent"]["side"]) \
        else "down" if sc_1d["percent"]["down"] > max(sc_1d["percent"]["up"], sc_1d["percent"]["side"]) \
        else "side"

    # ---------- 2) 4H: Zone ----------
    df_4h = get_data(SYMBOL, "4H")
    sc_4h = analyze_scenarios(df_4h, symbol=SYMBOL, tf="4H")
    fibo = sc_4h["levels"].get("fibo", {}) or {}
    print("\nfibo keys:", list(fibo.keys()))

    print("\n=== 2) FRAME: 4H (Zones/Setup) ===")
    print("percent:", sc_4h["percent"])
    print("fibo (จาก leg ล่าสุด):", fibo)
    _brief("ใช้ Fibo 0.5–0.618 เป็นโซนรีเทรซมาตรฐานของ pullback")

    def _fget(d, keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return None

    zones = {}
    if daily_bias == "up":
        rz_lo = _fget(fibo, ["retr_0.618", "0.618", "61.8", "61.8%"])
        rz_hi = _fget(fibo, ["retr_0.5", "0.5", "50", "50%"])
        zones["entry_zone"] = (rz_lo, rz_hi)
        zones["invalidate_below"] = sc_4h["levels"].get("recent_low")
        _brief("UP-bias → รอรีเทรซเข้า 0.618–0.5 หรือรอเบรกขึ้นบน 1H")
    elif daily_bias == "down":
        rz_lo = _fget(fibo, ["retr_0.5", "0.5", "50", "50%"])
        rz_hi = _fget(fibo, ["retr_0.618", "0.618", "61.8", "61.8%"])
        zones["entry_zone"] = (rz_lo, rz_hi)
        zones["invalidate_above"] = sc_4h["levels"].get("recent_high")
        _brief("DOWN-bias → รอรีบาวด์เข้า 0.5–0.618 หรือรอหลุดลงบน 1H")
    else:
        zones["range_edges"] = (sc_4h["levels"].get("recent_low"), sc_4h["levels"].get("recent_high"))
        _brief("SIDE-bias → เทรดกรอบ ขอบล่าง/บน")

    print("zones:", zones)

    # ---------- 3) 1H: Trigger ----------
    df_1h = get_data(SYMBOL, "1H")
    df_1h_ind = apply_indicators(df_1h)
    last = df_1h_ind.iloc[-1]
    recent_high_1h = float(df_1h["high"].tail(20).max())
    recent_low_1h  = float(df_1h["low"].tail(20).min())

    print("\n=== 3) FRAME: 1H (Trigger/Execution) ===")
    spot = {"close": float(last["close"]), "rsi14": float(last["rsi14"]), "macd_hist": float(last["macd_hist"])}
    print({"recent_high_1h": recent_high_1h, "recent_low_1h": recent_low_1h})
    print(spot)
    _brief("Long trigger: เบรก H1-high + RSI≥55 + MACD>0")
    _brief("Short trigger: หลุด H1-low + RSI≤45 + MACD<0")

    trigger = None
    tol = 0.0002  # 0.02% tolerance
    broke_high = bool(spot["close"] >= recent_high_1h * (1 - tol))
    broke_low  = bool(spot["close"] <= recent_low_1h  * (1 + tol))

    in_zone = False
    if zones.get("entry_zone"):
        rz_lo, rz_hi = zones["entry_zone"]
        in_zone = bool(rz_lo and rz_hi and (rz_lo <= spot["close"] <= rz_hi))

    if daily_bias == "up":
        if broke_high and (spot["rsi14"] >= 55) and (spot["macd_hist"] > 0):
            trigger = {"type": "LONG_BREAKOUT", "entry": spot["close"], "invalid_below": recent_low_1h}
        elif in_zone and (spot["rsi14"] >= 50):
            trigger = {"type": "LONG_PB", "entry": spot["close"], "invalid_below": recent_low_1h}
    elif daily_bias == "down":
        if broke_low and (spot["rsi14"] <= 45) and (spot["macd_hist"] < 0):
            trigger = {"type": "SHORT_BREAKDOWN", "entry": spot["close"], "invalid_above": recent_high_1h}
        elif in_zone and (spot["rsi14"] <= 50):
            trigger = {"type": "SHORT_PB", "entry": spot["close"], "invalid_above": recent_high_1h}
    else:
        if spot["close"] <= recent_low_1h and spot["rsi14"] < 40:
            trigger = {"type": "LONG_RANGE_REBOUND", "entry": spot["close"], "stop_below": recent_low_1h}
        elif spot["close"] >= recent_high_1h and spot["rsi14"] > 60:
            trigger = {"type": "SHORT_RANGE_FADE", "entry": spot["close"], "stop_above": recent_high_1h}

    print("trigger:", trigger)

    # ---------- 4) PLAN & ALERT ----------
    print("\nPLAN:")
    if daily_bias == "up":
        print(f"- Bias: LONG | H1 swing-high: {recent_high_1h:.2f} | Zone(4H): {zones.get('entry_zone')}")
        print("- A) Long-Breakout: รอปิดเหนือ H1-high + RSI≥55 + MACD>0 | SL ใต้ H1-low | TP: ext 1.272/1.618")
        print("- B) Long-Pullback: รอราคาย่อเข้า 0.618–0.5 & RSI≥50 มีแท่งยืนยัน | SL ใต้โซนหรือ H1-low")
    elif daily_bias == "down":
        print(f"- Bias: SHORT | H1 swing-low: {recent_low_1h:.2f} | Zone(4H): {zones.get('entry_zone')}")
        print("- A) Short-Breakdown: รอปิดใต้ H1-low + RSI≤45 + MACD<0 | SL เหนือ H1-high | TP: ext 1.272/1.618")
        print("- B) Short-Pullback: รอรีบาวด์เข้า 0.5–0.618 & RSI≤50 | SL เหนือโซนหรือ H1-high")
    else:
        print(f"- Bias: SIDE | Range: {zones.get('range_edges')}")
        print("- Mean Revert ที่ขอบกรอบ: เข้าที่ขอบ/แท่งยืนยันกลับ | SL เลยขอบ | TP กลางกรอบ/ฝั่งตรงข้าม")

    # ALERT: แจ้งเตือนเบื้องต้นเพื่อไม่พลาดจังหวะ
    if zones.get("entry_zone"):
        rz_lo, rz_hi = zones["entry_zone"]
        if rz_lo and rz_hi:
            if abs(spot["close"] - rz_lo) / rz_lo < 0.001 or abs(spot["close"] - rz_hi) / rz_hi < 0.001:
                print("ALERT: ราคาใกล้โซน 4H 0.618–0.5 แล้ว")
    if abs(spot["close"] - recent_high_1h) / max(recent_high_1h, 1) < 0.001:
        print("ALERT: ราคาใกล้เบรก H1-high")
    if abs(spot["close"] - recent_low_1h) / max(recent_low_1h, 1) < 0.001:
        print("ALERT: ราคาใกล้หลุด H1-low")

    # บอกเหตุผลถ้าไม่เข้าเงื่อนไข
    if not trigger:
        why = []
        if daily_bias == "up":
            if not broke_high:
                why.append("ยังไม่เบรก H1-high")
            if zones.get("entry_zone") and not in_zone:
                why.append("ยังไม่แตะโซน 0.618–0.5 (4H)")
        elif daily_bias == "down":
            if not broke_low:
                why.append("ยังไม่หลุด H1-low")
            if zones.get("entry_zone") and not in_zone:
                why.append("ยังไม่เข้าโซน 0.5–0.618 (4H)")
        if why:
            print("NOTE:", " ; ".join(why))

    # แนวคิดอินดิเคเตอร์ (สั้นๆ)
    _brief("1D: Dow+EMA50/200 ระบุเทรนด์หลัก; RSI/MACD คอนเฟิร์มโมเมนตัม")
    _brief("4H: ใช้ Fibo 0.5–0.618 เป็น PRZ ของ pullback")
    _brief("1H: ใช้ swing-break + RSI threshold + MACD hist เป็น Trigger")

if __name__ == "__main__":
    main()
