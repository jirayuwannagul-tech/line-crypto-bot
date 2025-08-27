from __future__ import annotations
import pandas as pd
from typing import Dict

def analyze_mtf_waves(path_1d="data/mtf/waves_1D.csv",
                      path_4h="data/mtf/waves_4H_mapped.csv",
                      path_1h="data/mtf/waves_1H_mapped.csv") -> Dict:
    w1d = pd.read_csv(path_1d, parse_dates=["start_ts","end_ts"])
    w4h = pd.read_csv(path_4h, parse_dates=["start_ts","end_ts","parent_start_ts","parent_end_ts"])
    w1h = pd.read_csv(path_1h, parse_dates=["start_ts","end_ts","parent_start_ts","parent_end_ts"])

    summary = []
    consistency_hits = 0
    total_segments = len(w1d)

    for _, main_wave in w1d.iterrows():
        s, e = main_wave["start_ts"], main_wave["end_ts"]
        # นับคลื่นย่อย 4H/1H ในช่วงนี้
        sub4 = w4h[(w4h["parent_start_ts"]==s)&(w4h["parent_end_ts"]==e)]
        sub1 = w1h[(w1h["parent_start_ts"]==s)&(w1h["parent_end_ts"]==e)]

        # ตรวจสอบ consistency แบบง่าย: ถ้ามี subwave >=3 ถือว่าผ่าน
        consistency_flag = (len(sub4)>=3 or len(sub1)>=5)
        if consistency_flag:
            consistency_hits += 1

        summary.append({
            "main_start": s, "main_end": e, "main_dir": main_wave["dir"],
            "subwaves_4H": len(sub4), "subwaves_1H": len(sub1),
            "consistent": consistency_flag
        })

    score = consistency_hits / total_segments if total_segments else 0.0

    return {
        "total_main_waves": total_segments,
        "consistency_score": round(score, 3),
        "details": summary
    }

if __name__ == "__main__":
    result = analyze_mtf_waves()
    print(f"MTF Consistency Score: {result['consistency_score']}")
    print("ตัวอย่างสรุป 5 แถวแรก:")
    for row in result["details"][:5]:
        print(row)
