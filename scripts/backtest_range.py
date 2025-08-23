# scripts/backtest_range.py
import pandas as pd
import argparse
from app.analysis import dow
import os
import pathlib

# ---------- Helpers ----------

def _read_price_file(path: str) -> pd.DataFrame:
    """
    อ่านไฟล์ราคามาตรฐาน (timestamp, open, high, low, close, volume)
    รองรับ .xlsx / .csv
    """
    if path is None:
        return None
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์: {path}")

    if p.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(str(p))
    else:
        df = pd.read_csv(str(p))

    # normalize
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _call_dow(df):
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # รองรับหลายชื่อฟังก์ชัน
    if hasattr(dow, "detect_swings"):
        res = dow.detect_swings(df)
    elif hasattr(dow, "detect_trend"):
        res = dow.detect_trend(df)
    elif hasattr(dow, "analyze_dow"):
        res = dow.analyze_dow(df)
    else:
        raise RuntimeError("dow.py ไม่มี detect_swings / detect_trend / analyze_dow")

    out = {"trend_primary": None, "trend_secondary": None, "confidence": None}
    if isinstance(res, dict):
        out["trend_primary"]   = res.get("trend_primary") or res.get("trend") or res.get("primary")
        out["trend_secondary"] = res.get("trend_secondary") or res.get("secondary")
        out["confidence"]      = res.get("confidence") or res.get("score") or res.get("prob")
    elif isinstance(res, (list, tuple)) and len(res) >= 1:
        out["trend_primary"] = res[0]
        if len(res) > 1: out["confidence"] = res[1]
    elif isinstance(res, str):
        out["trend_primary"] = res
    else:
        out["trend_primary"] = str(res)

    if out["trend_primary"] is None:
        raise RuntimeError(f"อ่านผลลัพธ์ Dow ไม่ได้: {res}")

    if isinstance(out["trend_primary"], str):
        out["trend_primary"] = out["trend_primary"].strip().upper()

    if out["confidence"] is None:
        out["confidence"] = 0
    return out


def _last_window(df: pd.DataFrame, end_ts, max_bars: int):
    """
    ดึง 'max_bars' แท่งล่าสุดก่อนเวลา end_ts (ไม่รวม end_ts)
    ใช้กับ 4H/1H เพื่อสรุปเทรนด์ล่าสุด
    """
    if df is None:
        return None
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    sub = df[df["timestamp"] < pd.to_datetime(end_ts)].tail(max_bars)
    return sub if not sub.empty else None


def _confirm_with_intraday(
    daily_trend: str,
    forward_start: str,
    h4_df: pd.DataFrame = None,
    h1_df: pd.DataFrame = None,
    lookback_bars_4h: int = 12,
    lookback_bars_1h: int = 24,
    allow_side_override: bool = False
):
    """
    ใช้ 4H/1H เป็น 'Trigger' ยืนยัน bias รายวัน (1D)
    - ถ้า daily_trend ∈ {UP, DOWN} → ต้องมีอย่างน้อยหนึ่งใน 4H/1H ที่ 'เห็นเทรนด์เดียวกัน' ในหน้าต่างล่าสุดก่อน forward_start
    - ถ้า daily_trend เป็น SIDE/NEUTRAL/FLAT และ allow_side_override=True:
        ถ้า 4H และ 1H 'เห็นเทรนด์เดียวกัน' (UP หรือ DOWN) → override ให้เป็นเทรนด์นั้น (เพื่อลด SIDE เกินจริง)

    Return: (confirmed: bool, reason: str, override_trend: str|None)
    """
    dtrend = (daily_trend or "").upper()
    bullish = {"UP"}
    bearish = {"DOWN"}
    sideish = {"SIDE", "NEUTRAL", "FLAT", "N/A", ""}

    # เตรียมหน้าต่างอินทราเดย์
    h4_win = _last_window(h4_df, forward_start, lookback_bars_4h) if h4_df is not None else None
    h1_win = _last_window(h1_df, forward_start, lookback_bars_1h) if h1_df is not None else None

    h4_trend = None
    h1_trend = None

    try:
        if h4_win is not None and len(h4_win) > 3:
            h4_trend = (_call_dow(h4_win).get("trend_primary") or "").upper()
    except Exception as e:
        h4_trend = None

    try:
        if h1_win is not None and len(h1_win) > 3:
            h1_trend = (_call_dow(h1_win).get("trend_primary") or "").upper()
    except Exception as e:
        h1_trend = None

    # กรณี daily เป็น UP/DOWN → ต้องมี intraday ยืนยัน
    if dtrend in bullish | bearish:
        if (h4_trend == dtrend) or (h1_trend == dtrend):
            return True, "TRIGGER_OK", None
        else:
            # ถ้าไม่มีไฟล์ intraday → ไม่บังคับ trigger
            if (h4_df is None) and (h1_df is None):
                return True, "NO_INTRADAY", None
            return False, "NO_TRIGGER", None

    # กรณี daily เป็น SIDE/NEUTRAL/FLAT
    if dtrend in sideish:
        if allow_side_override:
            # ต้องให้ 4H และ 1H 'เห็นเหมือนกัน' เพื่อปัด SIDE ให้เป็นทิศทาง
            if (h4_trend in bullish and h1_trend in bullish):
                return True, "OVERRIDE_SIDE_TO_UP", "UP"
            if (h4_trend in bearish and h1_trend in bearish):
                return True, "OVERRIDE_SIDE_TO_DOWN", "DOWN"
            # ถ้าไม่มีอินทราเดย์เลย → ยังใช้ได้ (ขึ้นอยู่กับ skip_side ภายนอก)
            if (h4_df is None) and (h1_df is None):
                return True, "NO_INTRADAY", None
            return False, "SIDE_NO_CONSENSUS", None
        else:
            # ไม่ override → ให้ชั้นนอกตัดสินด้วย skip_side ตามเดิม
            if (h4_df is None) and (h1_df is None):
                return True, "NO_INTRADAY", None
            return True, "INTRADAY_IGNORED_FOR_SIDE", None

    return True, "FALLBACK", None


# ---------- Backtest Core ----------

def backtest_range(
    df,
    start,
    end,
    save_path="backtest/results.csv",
    min_conf=0,
    skip_side=True,
    h4_path=None,
    h1_path=None,
    lookback_bars_4h=12,
    lookback_bars_1h=24,
    allow_side_override=False
):
    # ensure datetime + sort
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # intraday (optional)
    h4_df = _read_price_file(h4_path) if h4_path else None
    h1_df = _read_price_file(h1_path) if h1_path else None

    records = []
    periods = pd.date_range(start=start, end=end, freq="ME")  # month-end
    skipped = 0

    for i in range(len(periods) - 1):
        analysis_start = periods[i].replace(day=1).strftime("%Y-%m-%d")
        analysis_end   = periods[i].strftime("%Y-%m-%d")
        forward_start  = periods[i+1].replace(day=1).strftime("%Y-%m-%d")
        forward_end    = periods[i+1].strftime("%Y-%m-%d")

        analysis_df = df[(df['timestamp'] >= analysis_start) & (df['timestamp'] <= analysis_end)]
        forward_df  = df[(df['timestamp'] >= forward_start) & (df['timestamp'] <= forward_end)]

        print(f"\nตรวจสอบช่วง {analysis_start} → {analysis_end}")
        print("analysis rows:", len(analysis_df), " | forward rows:", len(forward_df))

        if analysis_df.empty or forward_df.empty:
            print("⚠️ ข้ามช่วงนี้เพราะไม่มีข้อมูลครบ")
            continue

        # 1) Daily bias
        res = _call_dow(analysis_df)
        trend_daily = (res.get("trend_primary") or "N/A").upper()
        confidence = float(res.get("confidence") or 0)

        # 2) Intraday confirm (4H/1H)
        confirmed, confirm_reason, override_trend = _confirm_with_intraday(
            daily_trend=trend_daily,
            forward_start=forward_start,
            h4_df=h4_df,
            h1_df=h1_df,
            lookback_bars_4h=lookback_bars_4h,
            lookback_bars_1h=lookback_bars_1h,
            allow_side_override=allow_side_override
        )

        trend_for_trade = override_trend or trend_daily

        # 3) Ground truth (เดือนถัดไป)
        start_price = float(forward_df.iloc[0]["open"])
        end_price   = float(forward_df.iloc[-1]["close"])
        real_trend = "UP" if end_price > start_price else "DOWN"

        # 4) Actionable rule
        actionable = True
        reason = ""
        if skip_side and trend_for_trade in {"SIDE", "NEUTRAL", "FLAT"}:
            actionable = False
            reason = "SIDE"
        if confidence < min_conf:
            actionable = False
            reason = (reason + "; " if reason else "") + f"CONF<{min_conf}"
        if not confirmed:
            actionable = False
            reason = (reason + "; " if reason else "") + confirm_reason

        hit = (trend_for_trade == real_trend) if actionable else None

        records.append({
            "analysis_start": analysis_start,
            "analysis_end": analysis_end,
            "trend_daily": trend_daily,
            "trend_pred": trend_for_trade,
            "confidence": confidence,
            "forward_start": forward_start,
            "forward_end": forward_end,
            "real_trend": real_trend,
            "actionable": int(actionable),
            "hit": (int(hit) if hit is not None else ""),
            "skip_reason": reason or confirm_reason
        })

        if actionable:
            print(f"ทำนาย(1D bias + trigger): {trend_for_trade} ({confidence:.0f}%) | "
                  f"ผลจริง {forward_start}→{forward_end}: {real_trend} | [{confirm_reason}]")
            print("✅ ตรง" if hit else "❌ ไม่ตรง")
        else:
            skipped += 1
            print(f"ℹ️ ไม่คิดรอบนี้ในความแม่นยำ "
                  f"(daily={trend_daily}, pred={trend_for_trade}, conf={confidence:.0f}%) → {reason or confirm_reason}")

    # 5) Summary
    result_df = pd.DataFrame(records)
    if not result_df.empty:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result_df.to_csv(save_path, index=False)
        print(f"\n✅ บันทึกผลลัพธ์ที่ {save_path}")

        used = result_df[result_df["actionable"] == 1]
        if not used.empty:
            acc = (used["hit"].astype(int).mean()) * 100
            print("\n=== สรุป Backtest (เฉพาะสัญญาณที่ใช้เทรดได้) ===")
            print(f"จำนวนรอบทั้งหมด: {len(result_df)} | ใช้งานได้: {len(used)} | ถูกข้าม: {skipped}")
            print(f"ตรง: {used['hit'].sum()} | ไม่ตรง: {len(used) - used['hit'].sum()}")
            print(f"ความแม่นยำ: {acc:.2f}%")
        else:
            print("\n⚠️ ไม่มีสัญญาณที่เข้าเงื่อนไขนำมาคิดความแม่นยำ")
    else:
        print("⚠️ ไม่มีข้อมูลที่ทดสอบได้")


# ---------- CLI ----------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--end", type=str, required=True)
    parser.add_argument("--out", type=str, default="backtest/results.csv")
    parser.add_argument("--min-conf", type=float, default=0, help="ขั้นต่ำความมั่นใจ เพื่อตัดสัญญาณทิ้งจากสถิติ")
    parser.add_argument("--no-skip-side", action="store_true", help="ถ้าใส่ flag นี้ จะนับ SIDE เป็นสัญญาณด้วย")

    # NEW: Intraday confirm options
    parser.add_argument("--h4", type=str, default=None, help="ไฟล์ราคา 4H (.xlsx หรือ .csv) มีคอลัมน์ timestamp,open,high,low,close,volume")
    parser.add_argument("--h1", type=str, default=None, help="ไฟล์ราคา 1H (.xlsx หรือ .csv) มีคอลัมน์ timestamp,open,high,low,close,volume")
    parser.add_argument("--lb4h", type=int, default=12, help="จำนวนแท่ง 4H ล่าสุดก่อนช่วง forward_start ที่ใช้สรุปเทรนด์")
    parser.add_argument("--lb1h", type=int, default=24, help="จำนวนแท่ง 1H ล่าสุดก่อนช่วง forward_start ที่ใช้สรุปเทรนด์")
    parser.add_argument("--allow-side-override", action="store_true",
                        help="อนุญาตให้ 4H และ 1H เห็นตรงกัน (UP/DOWN) แล้ว override สถานะ SIDE รายวันให้เป็นทิศนั้น")

    args = parser.parse_args()

    df = pd.read_excel("app/data/historical.xlsx")
    backtest_range(
        df,
        start=args.start,
        end=args.end,
        save_path=args.out,
        min_conf=args.min_conf,
        skip_side=not args.no_skip_side,
        h4_path=args.h4,
        h1_path=args.h1,
        lookback_bars_4h=args.lb4h,
        lookback_bars_1h=args.lb1h,
        allow_side_override=args.allow_side_override
    )
