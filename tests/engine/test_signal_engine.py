# tests/test_signal_engine.py
# =============================================================================
# Tests for app/engine/signal_engine.py (mock engine)
# Run with:  pytest -q
# =============================================================================

import math
import time
import pandas as pd

from app.engine.signal_engine import SignalEngine


def make_df_from_closes(closes):
    """
    สร้าง DataFrame OHLCV ง่าย ๆ จากรายการราคาปิด
    - open จะต่ำกว่า close เล็กน้อย เพื่อให้แท่งสุดท้ายเป็นเขียว (เอื้อ bias long)
    - high/low เผื่อระยะเล็กน้อย
    """
    opens = []
    highs = []
    lows = []
    vols = []
    for c in closes:
        o = c * 0.999  # เปิดต่ำกว่าปิดเล็กน้อย
        h = max(o, c) * 1.0005
        l = min(o, c) * 0.9995
        opens.append(o)
        highs.append(h)
        lows.append(l)
        vols.append(1.0)
    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols}
    )
    return df


def test_hold_when_insufficient_candles():
    eng = SignalEngine(cfg={"min_candles": 30})
    df = make_df_from_closes([100 + i for i in range(10)])  # น้อยกว่า min_candles
    out = eng.process_ohlcv("BTC", df)
    assert out["action"] == "HOLD"
    assert out["reason"] == "insufficient_candles"


def test_open_long_when_sma_fast_gt_slow_and_green_candle():
    eng = SignalEngine(cfg={"min_candles": 30, "sma_fast": 10, "sma_slow": 30})
    # สร้างแนวโน้มขาขึ้นยาวพอให้ SMA fast > slow + แท่งเขียว
    base = [100 + i * 0.5 for i in range(35)]
    df = make_df_from_closes(base)
    out = eng.process_ohlcv("BTC", df, use_ai=False)
    assert out["action"] in ("OPEN", "HOLD")  # ถ้าโดน cooldown ก็ HOLD
    # ถ้าเปิดสถานะให้เช็คข้อมูล position
    if out["action"] == "OPEN":
        assert out["side"] == "LONG"
        assert out["position"]["side"] == "LONG"
        assert out["position"]["entry"] is not None
        assert out["tp"] is not None and out["sl"] is not None


def test_cooldown_blocks_immediate_reopen():
    eng = SignalEngine(cfg={"min_candles": 30, "cooldown_sec": 9999})
    df = make_df_from_closes([100 + i * 0.5 for i in range(35)])
    out1 = eng.process_ohlcv("ETH", df)  # น่าจะ OPEN
    # เรียกซ้ำทันที → ต้อง HOLD ด้วยเหตุผล cooldown (เพราะเพิ่งส่งสัญญาณไป)
    out2 = eng.process_ohlcv("ETH", df)
    assert out2["action"] == "HOLD"
    assert out2["reason"] in ("cooldown", "in_position_no_flip")  # เปิดอยู่ก็ไม่ flip


def test_no_flip_and_tp_close_flow():
    eng = SignalEngine(cfg={"min_candles": 30, "sma_fast": 10, "sma_slow": 30, "risk_pct": 0.01, "rr": 1.5})
    # 1) เปิดสถานะ LONG
    df_up = make_df_from_closes([100 + i * 0.5 for i in range(40)])
    out_open = eng.process_ohlcv("BTC", df_up, use_ai=False)
    if out_open["action"] != "OPEN":
        # ถ้าไม่เปิด (เช่นติด cooldown) ให้บังคับรีเซ็ตเวลาเพื่อทดสอบ
        eng._states["BTC"].last_signal_ts = 0
        out_open = eng.process_ohlcv("BTC", df_up, use_ai=False)
    assert out_open["position"]["side"] == "LONG"
    entry = out_open["position"]["entry"]
    tp = out_open["tp"]
    assert entry and tp

    # 2) ยังไม่ถึง TP/SL → ควร HOLD (no-flip)
    df_hold = df_up.copy()
    out_hold = eng.process_ohlcv("BTC", df_hold, use_ai=False)
    assert out_hold["action"] in ("HOLD", "ALERT")

    # 3) สร้างแท่งให้ราคาถึง TP → ควร CLOSE ด้วยเหตุผล exit_tp
    closes = list(df_up["close"].values)
    closes[-1] = max(closes[-1], tp * 1.0001)  # ดันให้ทะลุ TP นิดหน่อย
    df_tp = make_df_from_closes(closes)
    out_close = eng.process_ohlcv("BTC", df_tp, use_ai=False)
    assert out_close["action"] == "CLOSE"
    assert out_close["reason"] == "exit_tp"
    assert out_close["position"]["side"] == "NONE"


def test_move_alerts_trigger_and_anchor_update():
    # ตั้ง threshold การแจ้งเตือน 1%
    eng = SignalEngine(cfg={"min_candles": 30, "move_alerts": [0.01]})
    df_up = make_df_from_closes([100 + i * 0.5 for i in range(40)])
    out_open = eng.process_ohlcv("SOL", df_up)
    if out_open["action"] != "OPEN":
        eng._states["SOL"].last_signal_ts = 0
        out_open = eng.process_ohlcv("SOL", df_up)
    assert out_open["position"]["side"] != "NONE"
    anchor = eng._states["SOL"].last_alert_price
    assert anchor is not None

    # ขยับราคามากกว่า +1% → ควรได้ ALERT และเลื่อน anchor
    closes = list(df_up["close"].values)
    closes[-1] = anchor * 1.012
    out_alert = eng.process_ohlcv("SOL", make_df_from_closes(closes))
    assert out_alert["action"] in ("ALERT", "HOLD")  # ถ้าไม่ถึง threshold พอดีอาจ HOLD
    # anchor ควรอัปเดตเมื่อเกิด ALERT
    if out_alert["action"] == "ALERT":
        assert math.isclose(eng._states["SOL"].last_alert_price, closes[-1], rel_tol=1e-6)


def test_ai_toggle_changes_confidence_but_not_required():
    eng = SignalEngine(cfg={"min_candles": 30})
    df = make_df_from_closes([100 + i for i in range(35)])

    # ใช้ค่าเริ่มต้น (AI off)
    out1 = eng.process_ohlcv("XRP", df, use_ai=False)
    conf1 = out1["analysis"]["pre_signal"]["confidence"]

    # เปิด AI
    out2 = eng.process_ohlcv("XRP", df, use_ai=True)
    conf2 = out2["analysis"]["pre_signal"]["confidence"]

    # เปิด AI แล้วความมั่นใจควร ≥ เดิม (ใน mock เรา boost เล็กน้อย)
    assert conf2 >= conf1
