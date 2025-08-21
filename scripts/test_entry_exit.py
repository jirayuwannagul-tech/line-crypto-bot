from app.analysis.timeframes import get_data
from app.analysis.entry_exit import suggest_trade

df = get_data("BTCUSDT", "1D")
signal = suggest_trade(df)

print("Trade Suggestion:")
print(signal)
