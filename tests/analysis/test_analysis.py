# scripts/test_analysis.py

from app.analysis.timeframes import get_data
from app.analysis.indicators import apply_indicators
from app.analysis.dow import analyze_dow
from app.analysis.elliott import analyze_elliott
from app.logic.scenarios import analyze_scenarios  # 🔄 แก้จาก app.analysis.scenarios

# 1) โหลดข้อมูล
df = get_data("BTCUSDT", "1D")

# 2) Indicators
df_ind = apply_indicators(df)

# 3) Dow
dow = analyze_dow(df_ind)
print("Dow:", dow)

# 4) Elliott
ell = analyze_elliott(df_ind)
print("Elliott:", {k: v for k, v in ell.items() if k != "debug"})

# 5) Scenarios (รวมทุกอย่าง)
sc = analyze_scenarios(df_ind, symbol="BTCUSDT", tf="1D")
print("Scenarios:", sc)
