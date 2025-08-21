# --- scripts/push_line_report.py (PATCH) ---
import os, requests
from analyze_chart import generate_report
from dotenv import load_dotenv
load_dotenv()  # โหลดค่าจากไฟล์ .env เข้ามาเป็น environment variables

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_PROFILE_URL = "https://api.line.me/v2/bot/profile/{userId}"

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
# ใช้ LINE_TO ถ้ามี; ถ้าไม่มีก็ fallback เป็น LINE_USER_ID
TO = os.environ.get("LINE_TO") or os.environ.get("LINE_USER_ID")

def chunk_text(text, limit=1800):
    chunks, buf, length = [], [], 0
    for line in text.splitlines():
        if length + len(line) + 1 > limit:
            chunks.append("\n".join(buf)); buf=[line]; length=len(line) + 1
        else:
            buf.append(line); length += len(line) + 1
    if buf: chunks.append("\n".join(buf))
    return chunks

def _headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def check_env():
    if not TOKEN or not TO:
        print("❌ Missing env: LINE_CHANNEL_ACCESS_TOKEN or LINE_TO/LINE_USER_ID")
        print("  export LINE_CHANNEL_ACCESS_TOKEN=... ; export LINE_TO=...  (หรือ LINE_USER_ID=...)")
        raise SystemExit(1)
    else:
        print(f"➡️ Using recipient: {TO[:6]}… (masked)")

def check_profile():
    # ใช้ได้เฉพาะ userId; ถ้าเป็น groupId/roomId จะได้ 400/404 (ข้ามไปส่งได้)
    url = LINE_PROFILE_URL.format(userId=TO)
    r = requests.get(url, headers=_headers(), timeout=20)
    if r.status_code == 200:
        print(f"✅ Profile OK for {TO}: {r.json().get('displayName','(no name)')}")
        return True
    elif r.status_code in (404, 400):
        print("ℹ️ Profile check not OK (404/400) — ถ้าใช้ groupId/roomId ถือว่าเป็นปกติ จะลองส่งต่อให้เลย")
    elif r.status_code in (401, 403):
        print(f"❌ Auth error {r.status_code}. ตรวจ Channel Access Token (scope/mismatch).")
    else:
        print(f"❌ Profile check error {r.status_code}: {r.text}")
    return False

def push_text(text):
    for chunk in chunk_text(text):
        payload = {"to": TO, "messages": [{"type": "text", "text": chunk}]}
        r = requests.post(LINE_PUSH_URL, headers=_headers(), json=payload, timeout=20)
        if r.status_code >= 300:
            print(f"❌ Push error {r.status_code}: {r.text}")
            if r.status_code == 401:
                print("   → Token ผิด/หมดอายุ/Channel ไม่ตรง")
            if r.status_code == 403:
                print("   → ไม่มีสิทธิ์ push ถึงผู้รับนี้ (ยังไม่เป็นเพื่อน/โดนบล็อก)")
            if r.status_code == 400:
                print("   → payload/TO ไม่ถูกต้อง หรือข้อความยาวเกิน (สคริปต์แบ่งแล้ว)")
            raise SystemExit(1)

def main():
    check_env()
    ok = check_profile()
    if not ok:
        print("⚠️ ข้าม profile check แล้วลองส่งเลย (กรณี groupId/roomId).")
    title = "📊 BTCUSDT Report (1D/4H/1H)"
    body = generate_report()
    print("→ Sending title…");  push_text(title)
    print("→ Sending report…"); push_text(body)
    print("✅ Pushed report to LINE")

if __name__ == "__main__":
    main()
