import requests

LINE_TOKEN = "YCvky4EDwOvZmzyw9ChiYpBLY4MvFqZZ+a9vC2Nt5mhhw3UQoRUQSw/hJIjtWoxtxnoOLHRevaI9g3sxhNpQlyW5Xkdhw51/jwVAVoPGhoFPUz8Xz9HfxJYRWQNr0YvTXhFoJlxe1+lNbnTUGBGzRgdB04t89/1O/w1cDnyilFU="

def send_message(user_id, text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    }
    r = requests.post(url, json=payload, headers=headers)
    print(r.status_code, r.text)

# เรียกใช้งาน
send_message("Ub8c49a8dd3f65586e24b5062c3c4472e", "ทดสอบข้อความสำเร็จ 🚀")
