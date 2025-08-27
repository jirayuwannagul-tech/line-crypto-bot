from __future__ import annotations
import os, json, sys
import pandas as pd
from dataclasses import dataclass
from typing import Tuple, Dict

DATA_DIR = "data"
OUT_DIR  = "data/mtf"
CSV_1D = os.path.join(DATA_DIR, "BTCUSDT_1D.csv")
CSV_4H = os.path.join(DATA_DIR, "BTCUSDT_4H.csv")
CSV_1H = os.path.join(DATA_DIR, "BTCUSDT_1H.csv")

os.makedirs(OUT_DIR, exist_ok=True)

@dataclass
class MTFWindow:
    start: pd.Timestamp
    end: pd.Timestamp
    rows_1d: int
    rows_4h: int
    rows_1h: int

def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    need_cols = {"timestamp","open","high","low","close","volume"}
    assert need_cols.issubset(df.columns), f"columns ไม่ครบใน {path}"
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df

def load_all() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    d1 = _load_csv(CSV_1D)
    d4 = _load_csv(CSV_4H)
    dH = _load_csv(CSV_1H)
    return d1, d4, dH

def compute_overlap(d1: pd.DataFrame, d4: pd.DataFrame, dH: pd.DataFrame) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start = max(d1["timestamp"].min(), d4["timestamp"].min(), dH["timestamp"].min())
    end   = min(d1["timestamp"].max(), d4["timestamp"].max(), dH["timestamp"].max())
    return start, end

def clip_to_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].reset_index(drop=True)

def save_outputs(d1: pd.DataFrame, d4: pd.DataFrame, dH: pd.DataFrame, meta: Dict):
    d1.to_csv(os.path.join(OUT_DIR, "BTCUSDT_1D_overlap.csv"), index=False)
    d4.to_csv(os.path.join(OUT_DIR, "BTCUSDT_4H_overlap.csv"), index=False)
    dH.to_csv(os.path.join(OUT_DIR, "BTCUSDT_1H_overlap.csv"), index=False)
    try:
        d1.to_parquet(os.path.join(OUT_DIR, "BTCUSDT_1D_overlap.parquet"), index=False)
        d4.to_parquet(os.path.join(OUT_DIR, "BTCUSDT_4H_overlap.parquet"), index=False)
        dH.to_parquet(os.path.join(OUT_DIR, "BTCUSDT_1H_overlap.parquet"), index=False)
    except Exception as e:
        print(f"warning: parquet save skipped ({e})", file=sys.stderr)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)

# -------------------------------
# NEW: prepare_mtf_struct()
# -------------------------------
def _load_overlap_or_raw():
    """โหลดไฟล์ overlap ถ้ามี ไม่มีก็โหลดจาก CSV ดิบแล้วคำนวณช่วงทับซ้อน"""
    p1 = os.path.join(OUT_DIR, "BTCUSDT_1D_overlap.csv")
    p4 = os.path.join(OUT_DIR, "BTCUSDT_4H_overlap.csv")
    pH = os.path.join(OUT_DIR, "BTCUSDT_1H_overlap.csv")
    if all(os.path.exists(p) for p in (p1,p4,pH)):
        d1 = pd.read_csv(p1, parse_dates=["timestamp"])
        d4 = pd.read_csv(p4, parse_dates=["timestamp"])
        dH = pd.read_csv(pH, parse_dates=["timestamp"])
        start, end = d1["timestamp"].min(), d1["timestamp"].max()
    else:
        d1, d4, dH = load_all()
        start, end = compute_overlap(d1, d4, dH)
        d1 = clip_to_window(d1, start, end)
        d4 = clip_to_window(d4, start, end)
        dH = clip_to_window(dH, start, end)
    return d1, d4, dH, start, end

def _merge_parent(df_child: pd.DataFrame, df_parent_1d: pd.DataFrame) -> pd.DataFrame:
    # จัดเตรียม key ของ 1D
    parents = df_parent_1d[["timestamp"]].rename(columns={"timestamp": "t1d"})
    # map แบบ asof: ให้แต่ละแท่งย่อยชี้ไปยังแท่ง 1D ล่าสุดก่อนหน้า (ไม่ข้ามอนาคต)
    out = pd.merge_asof(
        df_child.sort_values("timestamp"),
        parents.sort_values("t1d"),
        left_on="timestamp",
        right_on="t1d",
        direction="backward",
        allow_exact_matches=True
    )
    # กรองแถวที่ timestamp น้อยกว่าแท่ง 1D แรก (ไม่มี parent)
    out = out[out["t1d"].notna()].reset_index(drop=True)
    return out

def prepare_mtf_struct() -> Dict:
    """
    คืนค่าโครงสร้างพร้อมใช้:
    {
      'window': {'start':..., 'end':...},
      'frames': {'1d': df1d, '4h': df4h, '1h': df1h},
      'map': {'4h_to_1d': df4h_map, '1h_to_1d': df1h_map}
    }
    โดย df*_map มีคอลัมน์ 't1d' เป็น parent ของแต่ละแท่งย่อย
    """
    d1, d4, dH, start, end = _load_overlap_or_raw()

    # ทำ mapping 4H/1H -> 1D
    d4_map = _merge_parent(d4, d1)
    dH_map = _merge_parent(dH, d1)

    meta = {
        "window": {"start": start, "end": end},
        "rows": {"1D": len(d1), "4H": len(d4), "1H": len(dH)},
        "mapped_rows": {"4H_to_1D": len(d4_map), "1H_to_1D": len(dH_map)}
    }

    return {
        "window": meta["window"],
        "frames": {"1d": d1, "4h": d4, "1h": dH},
        "map": {"4h_to_1d": d4_map, "1h_to_1d": dH_map},
        "meta": meta
    }

def main():
    d1, d4, dH = load_all()
    start, end = compute_overlap(d1, d4, dH)

    d1w = clip_to_window(d1, start, end)
    d4w = clip_to_window(d4, start, end)
    dHw = clip_to_window(dH, start, end)

    meta = {
        "window": {"start": start, "end": end},
        "rows": {"1D": len(d1w), "4H": len(d4w), "1H": len(dHw)}
    }
    save_outputs(d1w, d4w, dHw, meta)

    print("== MTF Overlap Window ==")
    print(f"start={start}  end={end}")
    print("rows:", meta["rows"])
    print(f"✅ saved to: {OUT_DIR}/(BTCUSDT_*_overlap.csv|parquet, meta.json)")

if __name__ == "__main__":
    # ถ้ารันไฟล์ตรง ๆ จะทำการตัด overlap และเซฟ (พฤติกรรมเดิม)
    main()
