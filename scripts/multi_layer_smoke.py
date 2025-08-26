import json
from app.analysis.timeframes import get_data
from app.analysis.indicators import apply_indicators

SYMBOL = "BTCUSDT"
TF = "1H"

df = get_data(SYMBOL, TF)
if df is None or df.empty:
    raise SystemExit("❌ no data (check REALTIME=1 or files)")

dfi = apply_indicators(df.copy())
last = dfi.iloc[-1]  # แท่งล่าสุด

def f(key):
    return float(last[key]) if key in dfi.columns and last[key] == last[key] else None

out = {
    "symbol": SYMBOL,
    "tf": TF,
    "timestamp": str(last.get("timestamp")),
    "price_close": f("close"),
    "ema20": f("ema20"),
    "ema50": f("ema50"),
    "ema200": f("ema200"),
    "rsi14": f("rsi14"),
    "macd": f("macd"),
    "macd_signal": f("macd_signal"),
    "macd_hist": f("macd_hist"),
    "plus_di14": f("plus_di14"),
    "minus_di14": f("minus_di14"),
    "stoch_k": f("stoch_k"),
    "stoch_d": f("stoch_d"),
    "atr14": f("atr14"),
}
print(json.dumps(out, ensure_ascii=False, indent=2))
