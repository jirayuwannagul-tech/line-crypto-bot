from __future__ import annotations
import pandas as pd
from typing import List, Dict, Tuple

def _length(a: float, b: float) -> float:
    return b - a

def _abs(x: float) -> float:
    return x if x >= 0 else -x

def _ratio(part: float, base: float) -> float:
    if base == 0:
        return 0.0
    return part / base

def _in_range(x: float, lo: float, hi: float) -> bool:
    return (x >= lo) and (x <= hi)

def _ok_wave2_retrace(w1: Tuple[float,float], w2: Tuple[float,float], up: bool) -> bool:
    # retrace 0.2–0.8 ของ Wave1
    if up:
        r = _abs(_length(w1[1], w2[1])) / _abs(_length(w1[0], w1[1]))
    else:
        r = _abs(_length(w1[1], w2[1])) / _abs(_length(w1[0], w1[1]))
    return _in_range(r, 0.2, 0.8)

def _ok_wave3_extension(w1: Tuple[float,float], w3: Tuple[float,float], up: bool) -> bool:
    ext = _abs(_length(w3[0], w3[1])) / _abs(_length(w1[0], w1[1]))
    return ext >= 1.0  # ผ่อนคลายเป็น >=1.0 (แทน 1.618)

def _ok_wave4_retrace(w3: Tuple[float,float], w4: Tuple[float,float]) -> bool:
    r = _abs(_length(w3[1], w4[1])) / _abs(_length(w3[0], w3[1]))
    return _in_range(r, 0.1, 0.7)

def _no_overlap_up(w1: Tuple[float,float], w4_end: float) -> bool:
    # สำหรับ impulse ขาขึ้น: จุดจบคลื่น 4 ต้องไม่ต่ำกว่าจุดเริ่มคลื่น 1
    return w4_end > w1[0]

def _no_overlap_down(w1: Tuple[float,float], w4_end: float) -> bool:
    # สำหรับ impulse ขาลง: จุดจบคลื่น 4 ต้องไม่สูงกว่าจุดเริ่มคลื่น 1
    return w4_end < w1[0]

def _ok_wave5_length(w1: Tuple[float,float], w5: Tuple[float,float]) -> bool:
    # 0.382–1.618 ของ Wave1
    r = _abs(_length(w5[0], w5[1])) / _abs(_length(w1[0], w1[1]))
    return _in_range(r, 0.382, 1.618)

def _classify_impulse(seq: List[Dict]) -> Dict | None:
    """
    seq: รายการ 5 segments ต่อเนื่องจาก pivots [{'dir','start_px','end_px','start_ts','end_ts'}]
    คืนผลเป็น dict ถ้าผ่านเกณฑ์ impulse (up หรือ down)
    """
    dirs = [s['dir'] for s in seq]
    up_pattern = dirs == ['UP','DOWN','UP','DOWN','UP']
    down_pattern = dirs == ['DOWN','UP','DOWN','UP','DOWN']
    if not (up_pattern or down_pattern):
        return None

    up = up_pattern
    # wave tuples: (start_px, end_px)
    w1 = (seq[0]['start_px'], seq[0]['end_px'])
    w2 = (seq[1]['start_px'], seq[1]['end_px'])
    w3 = (seq[2]['start_px'], seq[2]['end_px'])
    w4 = (seq[3]['start_px'], seq[3]['end_px'])
    w5 = (seq[4]['start_px'], seq[4]['end_px'])

    # กฎเบื้องต้น
    ok2 = _ok_wave2_retrace(w1, w2, up)
    ok3 = _ok_wave3_extension(w1, w3, up)
    ok4 = _ok_wave4_retrace(w3, w4)
    nlap = _no_overlap_up(w1, w4[1]) if up else _no_overlap_down(w1, w4[1])
    ok5 = _ok_wave5_length(w1, w5)

    # wave3 ไม่สั้นที่สุด (เทียบกับ w1,w5)
    len1 = _abs(_length(*w1))
    len3 = _abs(_length(*w3))
    len5 = _abs(_length(*w5))
    w3_not_shortest = len3 >= min(len1, len5)

    checks = [ok2, ok3, ok4, nlap, ok5, w3_not_shortest]
    score = sum(1 for c in checks if c)

    if score >= 4:  # ผ่านขั้นต่ำ 4/6
        return {
            "type": "IMPULSE_UP" if up else "IMPULSE_DOWN",
            "start_ts": seq[0]['start_ts'],
            "end_ts": seq[4]['end_ts'],
            "score": score,
            "legs": [{
                "idx": i+1,
                "dir": seg["dir"],
                "start_ts": seg["start_ts"], "end_ts": seg["end_ts"],
                "start_px": seg["start_px"], "end_px": seg["end_px"]
            } for i, seg in enumerate(seq)]
        }
    return None

def _classify_correction(seq: List[Dict]) -> Dict | None:
    """
    รูปแบบ A-B-C อย่างง่าย: UP-DOWN-UP หรือ DOWN-UP-DOWN
    ตรวจ retrace และสัดส่วนกว้าง ๆ
    """
    dirs = [s['dir'] for s in seq]
    bull = dirs == ['DOWN','UP','DOWN']  # ในขาขึ้น: A ลง, B ขึ้น, C ลง
    bear = dirs == ['UP','DOWN','UP']    # ในขาลง: A ขึ้น, B ลง, C ขึ้น
    if not (bull or bear):
        return None

    A = (seq[0]['start_px'], seq[0]['end_px'])
    B = (seq[1]['start_px'], seq[1]['end_px'])
    C = (seq[2]['start_px'], seq[2]['end_px'])

    # สัดส่วนกว้าง ๆ: B retrace 0.3–0.8 ของ A, C ~ 0.618–1.618 ของ A
    rB = _abs(_length(B[0], B[1])) / _abs(_length(A[0], A[1])) if _abs(_length(*A))>0 else 0
    rC = _abs(_length(C[0], C[1])) / _abs(_length(A[0], A[1])) if _abs(_length(*A))>0 else 0

    okB = _in_range(rB, 0.3, 0.8)
    okC = _in_range(rC, 0.5, 1.8)

    score = int(okB) + int(okC)
    if score >= 1:
        return {
            "type": "CORRECTIVE_BULL" if bull else "CORRECTIVE_BEAR",
            "start_ts": seq[0]['start_ts'],
            "end_ts": seq[2]['end_ts'],
            "score": score,
            "legs": [{
                "label": l, "dir": seg["dir"],
                "start_ts": seg["start_ts"], "end_ts": seg["end_ts"],
                "start_px": seg["start_px"], "end_px": seg["end_px"]
            } for l, seg in zip(['A','B','C'], seq)]
        }
    return None

def classify_elliott_waves(segments: List[Dict]) -> List[Dict]:
    """
    รับอินพุตเป็น segments จาก ZigZag (ต่อเนื่องตามเวลา)
    คืนรายการผลลัพธ์ที่พบ (Impulse 5 คลื่น / Corrective ABC)
    """
    results: List[Dict] = []

    # สไลด์หน้าต่าง 5 คลื่นสำหรับ Impulse
    for i in range(0, len(segments) - 4):
        window5 = segments[i:i+5]
        r = _classify_impulse(window5)
        if r:
            results.append(r)

    # สไลด์หน้าต่าง 3 คลื่นสำหรับ Correction
    for i in range(0, len(segments) - 2):
        window3 = segments[i:i+3]
        r = _classify_correction(window3)
        if r:
            results.append(r)

    # จัดเรียงตามเวลาเริ่ม
    results.sort(key=lambda x: x["start_ts"])
    return results

def run_from_csv(in_csv: str, pct: float = 0.01, min_bars: int = 3, out_path: str = "data/mtf/classified_waves_1D.csv"):
    """
    โหลด CSV pivot (waves_1D.csv หากมีอยู่แล้วจะใช้เลย,
    ถ้าไม่มีจะพึ่งพา wave_points.detect_zigzag เพื่อสร้างขึ้นใหม่)
    """
    from app.analysis.wave_points import detect_zigzag

    try:
        df = pd.read_csv(in_csv, parse_dates=["start_ts","end_ts"])
        # แปลงเป็น segments dict
        segments = [{
            "start_ts": row["start_ts"], "end_ts": row["end_ts"],
            "start_px": float(row["start_px"]), "end_px": float(row["end_px"]),
            "dir": str(row["dir"])
        } for _, row in df.iterrows()]
    except Exception:
        # ถ้าไฟล์เป็นราคาแทน (timestamp, open, high, low, close, volume)
        price = pd.read_csv(in_csv, parse_dates=["timestamp"])
        segs = detect_zigzag(price, pct=pct, min_bars=min_bars)
        segments = [{
            "start_ts": s["start_ts"], "end_ts": s["end_ts"],
            "start_px": float(s["start_px"]), "end_px": float(s["end_px"]),
            "dir": s["dir"]
        } for s in segs]

    results = classify_elliott_waves(segments)
    # แปลงผลเป็นตารางแบน
    rows = []
    for r in results:
        row = {
            "type": r["type"],
            "start_ts": r["start_ts"],
            "end_ts": r["end_ts"],
            "score": r["score"],
        }
        rows.append(row)

    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_path, index=False)
    print(f"✅ saved {out_path} rows={len(out_df)}")

if __name__ == "__main__":
    # ดีฟอลต์อ่านจาก waves_1D.csv (pivots ที่เราสร้างไว้)
    run_from_csv("data/mtf/waves_1D.csv", pct=0.01, min_bars=3, out_path="data/mtf/classified_waves_1D.csv")
