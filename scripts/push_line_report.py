# --- scripts/push_line_report.py (NEW FILE) ---
import os
import math
import requests

# ดึงข้อความสรุปจากสคริปต์วิเคราะห์
from analyze_chart import generate_report

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")  # ใส่ Channel access token
TO = os.environ.get("LINE_TO")  # ใส่ userId / roomId / groupId ที่จะส่งหา

def chunk_text(text, limit=1800):
    # กันข้อความยาวเกินลิมิตต่อข้อความ (เผื่อ margin จากขีด 2000 ของ LINE)
    chunks = []
    buf = []
    length = 0
    for line in text.splitlines():
        if length + len(line) + 1 > limit:
            chunks.append("\n".join(buf))
            buf = [line]
            length = len(line) + 1
        else:
            buf.append(line)
            length += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks

def push_text(text):
    if not TOKEN or not TO:
        raise RuntimeError("Please set LINE_CHANNEL_ACCESS_TOKEN and LINE_TO in environment.")
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    for chunk in chunk_text(text):
        payload = {
            "to": TO,
            "messages": [
                {"type": "text", "text": chunk}
            ]
        }
        resp = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()

def main():
    report = generate_report()
    # ใส่หัวเรื่องสั้น ๆ แยกกล่องแรก
    title = "📊 BTCUSDT Report (1D/4H/1H)"
    push_text(title)
    push_text(report)
    print("Pushed report to LINE successfully.")

if __name__ == "__main__":
    main()
