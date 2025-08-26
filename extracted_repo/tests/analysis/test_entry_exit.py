# scripts/test_entry_exit.py

from app.analysis.timeframes import get_data
from app.analysis.entry_exit import suggest_trade

# 1) โหลดข้อมูล
df = get_data("BTCUSDT", "1D")

# 2) เรียก suggest_trade
signal = suggest_trade(df)

# 3) แสดงผล
print("Trade Suggestion:")
print(signal)
