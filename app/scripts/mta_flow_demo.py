# scripts/mta_flow_demo.py
# อธิบาย: เดินทีละกรอบเวลา 1D→4H→1H เพื่อหาจุดเข้าออก แบบยึดหลัก Dow/Indicators/Fibo

from app.analysis.timeframes import get_data
from app.analysis.scenarios import analyze_scenarios
from app.analysis.indicators import apply_indicators
import pandas as pd

SYMBOL = "BTCUSDT"

def _brief(line: str):
    print(f"- {line}")

def main():
    # ---------- 1) Daily: เข็มทิศ (กำหนด Bias) ----------
    df_1d = get_data(SYMBOL, "1D")
    sc_1d = analyze_scenarios(df_1d, symbol=SYMBOL, tf="1D")

    print("\n=== 1) FRAME: 1D (Bias/Context) ===")
    print("percent:", sc_1d["percent"])
    print("levels:", {k: sc_1d["levels"].get(k) for k in ["ema50", "ema200", "recent_high", "recent_low"]})
    _brief("ใช้ Dow Structure + EMA(50/200) เป็นแกน: ถ้า close/EMA50 > EMA200 → โครงสร้างกระทิง (หลัก Dow+EMA)")
    _brief("RSI>55, MACD hist>0 → โมเมนตัมหนุนขาขึ้น (กฏ RSI/MACD พื้นฐาน)")
    _brief("ถ้า 1D = UP ให้มองหา long ในกรอบย่อย; ถ้า DOWN ให้มองหา short")

    daily_bias = "up" if sc_1d["percent"]["up"] > max(sc_1d["percent"]["down"], sc_1d["percent"]["side"]) \
        else "down" if sc_1d["percent"]["down"] > max(sc_1d["percent"]["up"], sc_1d["percent"]["side"]) \
        else "side"

    # ---------- 2) 4H: แผนที่ (หาโซนเข้า) ----------
    df_4h = get_data(SYMBOL, "4H")
    sc_4h = analyze_scenarios(df_4h, symbol=SYMBOL, tf="4H")
    fibo = sc_4h["levels"].get("fibo", {}) or {}

    print("\n=== 2) FRAME: 4H (Zones/Setup) ===")
    print("percent:", sc_4h["percent"])
    print("fibo (จาก leg ล่าสุด):", fibo)
    _brief("ใช้ Fibo 0.382/0.5/0.618 ของขาแกว่งล่าสุดเป็นจุดรับ/ขาย (หลัก Fibo retracement)")
    _brief("ใช้ recent_high/low เป็นแนวเบรก/ต้านรับตามโครงสร้างสวิง (หลักการสวิงไฮ/โลว์)")

    # เสนอ “โซนเข้า” ตาม bias รายวัน
    zones = {}
    if daily_bias == "up":
        zones["entry_zone"] = (fibo.get("0.5"), fibo.get("0.618"))  # PRZ ซื้อจากรีเทรซกลาง-ลึก
        zones["invalidate_below"] = sc_4h["levels"].get("recent_low")
        _brief("Bias UP → รอรีเทรซลงมาบริเวณ 0.5–0.618 เพื่อ Long (ตามหลัก Trend Pullback)")
    elif daily_bias == "down":
        zones["entry_zone"] = (fibo.get("0.5"), fibo.get("0.618"))  # โซนขายเมื่อรีบาวด์ขึ้น
        zones["invalidate_above"] = sc_4h["levels"].get("recent_high")
        _brief("Bias DOWN → รอรีบาวด์ขึ้นมาบริเวณ 0.5–0.618 เพื่อ Short (Mean to Trend)")
    else:
        zones["range_edges"] = (sc_4h["levels"].get("recent_low"), sc_4h["levels"].get("recent_high"))
        _brief("Bias SIDE → เทรดกรอบ สลับรับที่ขอบล่าง/ขายที่ขอบบน (Range Trading)")

    print("zones:", zones)

    # ---------- 3) 1H: ทริกเกอร์ (สั่งยิง) ----------
    df_1h = get_data(SYMBOL, "1H")
    df_1h_ind = apply_indicators(df_1h)  # ต้องใช้ RSI/MACD ล่าสุดยืนยัน
    last = df_1h_ind.iloc[-1]
    recent_high_1h = float(df_1h["high"].tail(20).max())
    recent_low_1h = float(df_1h["low"].tail(20).min())

    print("\n=== 3) FRAME: 1H (Trigger/Execution) ===")
    print({"close": float(last["close"]), "rsi14": float(last["rsi14"]), "macd_hist": float(last["macd_hist"])})
    _brief("ทริกเกอร์ Long: เบรกเหนือ swing-high ล่าสุด + RSI>55 + MACD hist>0 (กฏโมเมนตัม + เบรกแนว)")
    _brief("ทริกเกอร์ Short: หลุดใต้ swing-low ล่าสุด + RSI<45 + MACD hist<0 (กฏโมเมนตัมขาลง + เบรกแนว)")

    trigger = None
    if daily_bias == "up":
        if (last["close"] > recent_high_1h) and (last["rsi14"] >= 55) and (last["macd_hist"] > 0):
            trigger = {"type": "LONG_BREAKOUT", "entry": float(last["close"]), "invalid_below": recent_low_1h}
        elif zones.get("entry_zone"):
            rz_lo, rz_hi = zones["entry_zone"]
            if rz_lo and rz_hi and (rz_lo <= last["close"] <= rz_hi) and (last["rsi14"] >= 50):
                trigger = {"type": "LONG_PB", "entry": float(last["close"]), "invalid_below": recent_low_1h}
    elif daily_bias == "down":
        if (last["close"] < recent_low_1h) and (last["rsi14"] <= 45) and (last["macd_hist"] < 0):
            trigger = {"type": "SHORT_BREAKDOWN", "entry": float(last["close"]), "invalid_above": recent_high_1h}
        elif zones.get("entry_zone"):
            rz_lo, rz_hi = zones["entry_zone"]
            if rz_lo and rz_hi and (rz_lo <= last["close"] <= rz_hi) and (last["rsi14"] <= 50):
                trigger = {"type": "SHORT_PB", "entry": float(last["close"]), "invalid_above": recent_high_1h}
    else:
        # SIDE: เทรด mean-revert ที่ขอบกรอบ
        if last["close"] <= recent_low_1h and last["rsi14"] < 40:
            trigger = {"type": "LONG_RANGE_REBOUND", "entry": float(last["close"]), "stop_below": recent_low_1h}
        elif last["close"] >= recent_high_1h and last["rsi14"] > 60:
            trigger = {"type": "SHORT_RANGE_FADE", "entry": float(last["close"]), "stop_above": recent_high_1h}

    print("trigger:", trigger)

    # ---------- 4) SL/TP guideline (สั้น ๆ ตามหลักทั่วไป) ----------
    if trigger:
        _brief("SL: วางหลังสวิงฝั่งตรงข้าม 1H (ตามหลักโครงสร้างสวิง) หรือระยะ ATR(14)≈1–1.5 เท่าของกรอบ")
        _brief("TP: ใช้ Fibo extension 1.272/1.618 ของขาเบรก หรือ EMA/สวิงถัดไปเป็นเป้าหมาย (กฏ Fibo/Moving Target)")

if __name__ == "__main__":
    main()
