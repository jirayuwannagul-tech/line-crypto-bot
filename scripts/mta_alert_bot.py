# scripts/mta_alert_bot.py
# แจ้งเตือน MTA: 1D→4H→1H  (Breakout / Pullback Zone / ใกล้เงื่อนไข)
from __future__ import annotations
import os
from typing import Optional, Tuple

from dotenv import load_dotenv
load_dotenv()  # โหลด .env (ต้องมี LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, PYTHONPATH=.)

from app.analysis.timeframes import get_data
from app.logic.scenarios import analyze_scenarios   # ✅ แก้ import มาที่ logic
from app.analysis.indicators import apply_indicators

# ====== CONFIG ======
SYMBOLS = os.getenv("MTA_SYMBOLS", "BTCUSDT").split(",")
BREAK_TOL = float(os.getenv("MTA_BREAK_TOL", "0.0005"))   # 0.05%
ZONE_TOL  = float(os.getenv("MTA_ZONE_TOL",  "0.0010"))   # 0.10%

# LINE Push (ตรง ๆ ด้วย SDK v3)
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")  # ต้องมี
LINE_TO    = os.getenv("LINE_USER_ID")               # ต้องมี

def _fmt(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:,.2f}"

def _send_line(text: str):
    """ส่ง Push เข้า LINE ถ้า token และ user id พร้อม; ไม่งั้น print"""
    if LINE_TOKEN and LINE_TO:
        try:
            from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
            cfg = Configuration(access_token=LINE_TOKEN)
            with ApiClient(cfg) as client:
                MessagingApi(client).push_message(
                    PushMessageRequest(to=LINE_TO, messages=[TextMessage(text=text[:4900])])
                )
            print("✅ [LINE] sent")
            return
        except Exception as e:
            print(f"[LINE ERROR] {e} -> fallback print")
    print(text)

def _brief(msg: str) -> str:
    return f"• {msg}"

def _pick_bias(percent: dict) -> str:
    up, down, side = percent["up"], percent["down"], percent["side"]
    if up > down and up > side: return "up"
    if down > up and down > side: return "down"
    return "side"

def _fib_zone(levels_fibo: dict, bias: str) -> Optional[Tuple[float, float]]:
    if not levels_fibo: return None
    lo = levels_fibo.get("retr_0.618")
    hi = levels_fibo.get("retr_0.5")
    if lo is None or hi is None: return None
    return (float(lo), float(hi))

def run_symbol(symbol: str):
    # 1) 1D → bias
    df_1d = get_data(symbol, "1D")
    sc_1d = analyze_scenarios(df_1d, symbol=symbol, tf="1D")
    bias = _pick_bias(sc_1d["percent"])

    # 2) 4H → zone/invalidate
    df_4h = get_data(symbol, "4H")
    sc_4h = analyze_scenarios(df_4h, symbol=symbol, tf="4H")
    fibo = (sc_4h["levels"] or {}).get("fibo", {}) or {}
    zone = _fib_zone(fibo, bias)
    invalidate = (sc_4h["levels"] or {}).get("recent_low") if bias == "up" else (sc_4h["levels"] or {}).get("recent_high")

    # 3) 1H → trigger context
    df_1h = get_data(symbol, "1H")
    df_1h_ind = apply_indicators(df_1h)
    last = df_1h_ind.iloc[-1]
    close = float(last["close"]); rsi = float(last["rsi14"]); macd_hist = float(last["macd_hist"])
    recent_high_1h = float(df_1h["high"].tail(20).max())
    recent_low_1h  = float(df_1h["low"].tail(20).min())

    broke_high = close >= recent_high_1h * (1 - BREAK_TOL)
    broke_low  = close <= recent_low_1h  * (1 + BREAK_TOL)

    in_zone = False
    if zone:
        zlo, zhi = zone
        in_zone = (zlo <= close <= zhi)

    # --------- compose alert text ---------
    header = f"[MTA Alert] {symbol}  |  Bias(1D): {bias.upper()}"
    lines = [header]

    if bias == "up":
        lines.append(_brief(f"4H Zone (0.618–0.5): { _fmt(zone[0]) if zone else '-' }–{ _fmt(zone[1]) if zone else '-' } | Invalidate < {_fmt(invalidate)}"))
        lines.append(_brief(f"1H Swing-High: {_fmt(recent_high_1h)} | Swing-Low: {_fmt(recent_low_1h)}"))
        lines.append(_brief("A) Long-Breakout: ปิดเหนือ H1-high + RSI≥55 + MACD>0"))
        lines.append(_brief("B) Long-Pullback: ย่อเข้าโซน (0.618–0.5) + RSI≥50"))
    elif bias == "down":
        lines.append(_brief(f"4H Zone (0.5–0.618): { _fmt(zone[0]) if zone else '-' }–{ _fmt(zone[1]) if zone else '-' } | Invalidate > {_fmt(invalidate)}"))
        lines.append(_brief(f"1H Swing-High: {_fmt(recent_high_1h)} | Swing-Low: {_fmt(recent_low_1h)}"))
        lines.append(_brief("A) Short-Breakdown: ปิดใต้ H1-low + RSI≤45 + MACD<0"))
        lines.append(_brief("B) Short-Pullback: รีบาวด์เข้าโซน (0.5–0.618) + RSI≤50"))
    else:
        lines.append(_brief(f"Range Mode: {_fmt((sc_4h['levels'] or {}).get('recent_low'))} – {_fmt((sc_4h['levels'] or {}).get('recent_high'))}"))
        lines.append(_brief(f"1H Swing-High: {_fmt(recent_high_1h)} | Swing-Low: {_fmt(recent_low_1h)}"))

    lines.append(_brief(f"Now: Close={_fmt(close)} | RSI14={rsi:.1f} | MACD_hist={macd_hist:.2f}"))

    if bias == "up":
        if abs(close - recent_high_1h) / max(recent_high_1h, 1) < ZONE_TOL:
            lines.append("⚠️ ใกล้เบรก H1-high")
        if zone:
            zlo, zhi = zone
            if abs(close - zlo) / zlo < ZONE_TOL or abs(close - zhi) / zhi < ZONE_TOL:
                lines.append("⚠️ ราคาใกล้โซน 4H 0.618–0.5")
        if broke_high and rsi >= 55 and macd_hist > 0:
            lines.append("✅ สัญญาณเข้า: LONG_BREAKOUT (ผ่านเงื่อนไข)")
        elif in_zone and rsi >= 50:
            lines.append("✅ สัญญาณเข้า: LONG_PB (ผ่านเงื่อนไข)")
    elif bias == "down":
        if abs(close - recent_low_1h) / max(recent_low_1h, 1) < ZONE_TOL:
            lines.append("⚠️ ใกล้หลุด H1-low")
        if zone:
            zlo, zhi = zone
            if abs(close - zlo) / zlo < ZONE_TOL or abs(close - zhi) / zhi < ZONE_TOL:
                lines.append("⚠️ ราคาใกล้โซน 4H 0.5–0.618")
        if broke_low and rsi <= 45 and macd_hist < 0:
            lines.append("✅ สัญญาณเข้า: SHORT_BREAKDOWN (ผ่านเงื่อนไข)")
        elif in_zone and rsi <= 50:
            lines.append("✅ สัญญาณเข้า: SHORT_PB (ผ่านเงื่อนไข)")
    else:
        if abs(close - recent_high_1h) / max(recent_high_1h, 1) < ZONE_TOL:
            lines.append("⚠️ ใกล้ขอบบนกรอบ (พิจารณา Fade)")
        if abs(close - recent_low_1h) / max(recent_low_1h, 1) < ZONE_TOL:
            lines.append("⚠️ ใกล้ขอบล่างกรอบ (พิจารณา Rebound)")

    _send_line("\n".join(lines))

def main():
    for sym in SYMBOLS:
        run_symbol(sym.strip().upper())

if __name__ == "__main__":
    # เผื่อรันแบบตรง ๆ; ถ้ารันด้วย `python -m scripts.mta_alert_bot` ก็ไม่ต้องตั้ง PYTHONPATH
    if not os.getenv("PYTHONPATH"):
        os.environ["PYTHONPATH"] = "."
    main()
