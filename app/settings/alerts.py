from __future__ import annotations

ALERT_RULES = {
    "ema_trend": True,          # Long: close>ema50>=ema200, Short: close<ema50<=ema200
    "prob_strong": 60,          # เกณฑ์แข็งแรง
    "prob_soft": 55,            # เกณฑ์อ่อน (ถ้าตรง trend)
    "atr_min_pct": 0.004,       # อย่างน้อย ~0.4%
    "weekly_guard": True,       # ไม่สวน weekly bias เว้น prob ≥ 65
    "weekly_override": 65,
    "debounce_minutes": 90,     # กันสแปม
}
