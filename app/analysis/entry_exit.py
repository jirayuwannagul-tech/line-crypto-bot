# app/analysis/entry_exit.py
from __future__ import annotations
from typing import Dict, Optional

import pandas as pd
import numpy as np

from .scenarios import analyze_scenarios

__all__ = ["suggest_trade"]

def suggest_trade(
    df: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    tf: str = "1D",
    cfg: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    สร้างคำแนะนำจุดเข้า TP/SL จากผล scenarios
    """
    sc = analyze_scenarios(df, symbol=symbol, tf=tf, cfg=cfg or {})
    last = df.iloc[-1]
    close = float(last["close"])

    direction = max(sc["percent"], key=sc["percent"].get)  # up/down/side
    entry: Optional[float] = None
    sl: Optional[float] = None
    tps: Dict[str, float] = {}

    # --- Entry / SL / TP Logic ---
    if direction == "up":
        entry = close
        sl = sc["levels"].get("recent_low")
        fibo = sc["levels"].get("fibo", {})
        if fibo:
            tps = {
                "TP1": fibo.get("ext_1.272"),
                "TP2": fibo.get("ext_1.618"),
            }
    elif direction == "down":
        entry = close
        sl = sc["levels"].get("recent_high")
        fibo = sc["levels"].get("fibo", {})
        if fibo:
            tps = {
                "TP1": fibo.get("retr_0.382"),
                "TP2": fibo.get("retr_0.5"),
                "TP3": fibo.get("retr_0.618"),
            }
    else:
        # side → ไม่แนะนำ entry
        entry = None
        sl = None

    return {
        "symbol": symbol,
        "tf": tf,
        "direction": direction,
        "entry": entry,
        "stop_loss": sl,
        "take_profits": {k: v for k, v in tps.items() if v},
        "scenarios": sc,  # แนบผลเต็มไว้ด้วย
    }
