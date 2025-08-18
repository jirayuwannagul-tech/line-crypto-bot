import json
import logging
from fastapi import APIRouter, Header, HTTPException, Request

from app.utils.settings import settings
from app.adapters.line.client import verify_signature, reply_message
from app.utils.crypto_price import fetch_price

router = APIRouter()
logger = logging.getLogger(__name__)

# แมปคำสั่ง -> สัญลักษณ์บน Binance (USDT คู่)
SYMBOL_MAP = {
    "BTC":  "BTCUSDT",
    "ETH":  "ETHUSDT",
    "ETC":  "ETCUSDT",
    "SOL":  "SOLUSDT",
    "ARP":  "ARBUSDT",   # เผื่อพิมพ์ผิดจาก ARB
    "ARB":  "ARBUSDT",
    "XRP":  "XRPUSDT",   # เพิ่มไว้เผื่อใช้
    "HBAR": "HBARUSDT",
    "ADA":  "ADAUSDT",
    "DOGE": "DOGEUSDT",
    "SAND": "SANDUSDT",
}

def fmt_price(p: float) -> str:
    return f"{p:,.2f}" if p >= 1 else f"{p:,.6f}"

@router.get("/webhook")
def webhook_verify():
    return {"status": "ok"}

@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, alias="X-Line-Signature"),
):
    settings.validate_line()

    body = await request.body()
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature")

    if not verify_signature(settings.LINE_CHANNEL_SECRET, body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    events = data.get("events", [])
    for ev in events:
        if ev.get("type") == "message" and ev.get("message", {}).get("type") == "text":
            reply_token = ev.get("replyToken")
            text = (ev.get("message", {}).get("text") or "").strip()
            if not reply_token:
                continue

            s = text.upper()

            # ราคาคริปโตหลายตัวตามแมป
            if s in SYMBOL_MAP:
                pair = SYMBOL_MAP[s]
                try:
                    price = await fetch_price(pair)
                    await reply_message(reply_token, [
                        {"type": "text", "text": f"{s}/USDT ~ {fmt_price(price)}"}
                    ])
                except Exception:
                    await reply_message(reply_token, [
                        {"type": "text", "text": f"ดึงราคา {s} ไม่สำเร็จ ลองใหม่ครับ 🙏"}
                    ])
                continue

            # คำทักทายพื้นฐาน
            if s in {"สวัสดี", "ดีดี", "ดีจ้า"}:
                await reply_message(reply_token, [
                    {"type": "text", "text": "สวัสดีครับ 🙏"}
                ])
            else:
                await reply_message(reply_token, [
                    {"type": "text", "text": f"คุณว่า: {text}"}
                ])

    return {"status": "ok", "events": len(events)}
