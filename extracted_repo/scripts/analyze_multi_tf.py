import json
from app.analysis.timeframes import get_data
from app.analysis.indicators import apply_indicators
from app.analysis.dow import analyze_dow
from app.analysis import elliott as ew  # ต้องมี ew.analyze_elliott

SYMBOL = "BTCUSDT"

def pack_last(df):
    last = df.iloc[-1]
    take = {}
    for k in ("timestamp","close","ema20","ema50","ema200","rsi14","macd","macd_signal","macd_hist","plus_di14","minus_di14","stoch_k","stoch_d"):
        if k in df.columns:
            v = last[k]
            take[k] = None if v!=v else (float(v) if hasattr(v,"__float__") else str(v))
    return take

out = {"symbol": SYMBOL, "pipeline": []}

# 1) 1H
df_1h = get_data(SYMBOL, "1H")
if df_1h is None or df_1h.empty:
    raise SystemExit("❌ 1H: no data (check REALTIME=1 or files)")
df_1h_i = apply_indicators(df_1h.copy())
dow_1h = {}
try:
    dow_1h = analyze_dow(df_1h_i.copy())
except Exception as e:
    dow_1h = {"error": str(e)}

out["pipeline"].append({
    "tf": "1H",
    "indicators_last": pack_last(df_1h_i),
    "dow": dow_1h if isinstance(dow_1h, dict) else str(dow_1h),
})

# 2) 4H
df_4h = get_data(SYMBOL, "4H")
if df_4h is None or df_4h.empty:
    raise SystemExit("❌ 4H: no data (check REALTIME=1 or files)")
df_4h_i = apply_indicators(df_4h.copy())
dow_4h = {}
try:
    dow_4h = analyze_dow(df_4h_i.copy())
except Exception as e:
    dow_4h = {"error": str(e)}

out["pipeline"].append({
    "tf": "4H",
    "indicators_last": pack_last(df_4h_i),
    "dow": dow_4h if isinstance(dow_4h, dict) else str(dow_4h),
})

# 3) Elliott (มองภาพใหญ่จาก 4H)
elliott = {}
try:
    ell = ew.analyze_elliott(df_4h_i.copy())
    elliott = ell if isinstance(ell, dict) else {"result": str(ell)}
except Exception as e:
    elliott = {"error": str(e)}

out["elliott_4h"] = elliott

print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
