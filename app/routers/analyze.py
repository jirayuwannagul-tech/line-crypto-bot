# app/routers/analyze.py
from fastapi import APIRouter
import numpy as np
import pandas as pd
from app.analysis.scenarios import analyze_scenarios

router = APIRouter(prefix="/analyze", tags=["analyze"])

@router.get("/mock")
def mock_analysis(symbol: str = "BTCUSDT", tf: str = "1D"):
    # สร้างข้อมูลจำลอง
    np.random.seed(0)
    close = np.cumsum(np.random.randn(150)) + 50000
    high  = close + np.abs(np.random.randn(150)) * 50
    low   = close - np.abs(np.random.randn(150)) * 50
    open_ = close + np.random.randn(150)
    vol   = np.random.randint(100, 1000, size=150)

    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": vol
    })
    payload = analyze_scenarios(df, symbol=symbol, tf=tf)
    return {"symbol": symbol, "tf": tf, "payload": payload}
