# app/routers/line_webhook.py
from __future__ import annotations

import os
import re
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from app.features.replies.keyword_reply import (
    get_reply,
    parse_price_command,
    parse_analysis_mock,
    parse_analyze_command,
)

# วิเคราะห์จริง
from app.analysis.timeframes import get_data
from app.analysis.scenarios import analyze_scenarios

# ตั้งแจ้งเตือนราคา (ใช้ร่วมกับ background loop ที่ start ใน app/main.py)
from app.features.alerts.price_reach import add_watch, remove_watch

# LINE SDK v3
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage as LineTextMessage,
)
from linebot.v3.webhooks import (
    WebhookParser,
    MessageEvent,
    TextMessageContent,
)
from linebot.v3.exceptions import InvalidSignatureError

router = APIRouter()

# ====== ENV ======
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# สร้าง parser และ config ของ LINE (ปล่อยว่างไว้ก่อนถ้าไม่มี env)
_parser: Optional[WebhookParser] = WebhookParser(CHANNEL_SECRET) if CHANNEL_SECRET else None
_config: Optional[Configuration] = Configuration(access_token=CHANNEL_ACCESS_TOKEN) if CHANNEL_ACCESS_TOKEN else None

# ====== คำสั่งตั้ง/ยกเลิกแจ้งเตือนราคา ======
# ตัวอย่าง:
#   "ตั้งเข้า BTCUSDT 60000"         → tol=0
#   "watch btc 60000 tol=50"         → tol=50
#   "ยกเลิกเข้า BTCUSDT" / "unwatch btc"
_WATCH_SET = re.compile(
    r"^(?:ตั้งเข้า|watch)\s+([A-Za-z0-9:/._-]+)\s+([0-9]+(?:\.[0-9]+)?)(?:\s+tol=(\d+(?:\.\d+)?))?$",
    re.IGNORECASE,
)
_WATCH_DEL = re.compile(
    r"^(?:ยกเลิกเข้า|unwatch)\s+([A-Za-z0-9:/._-]+)$",
    re.IGNORECASE,
)

# ====== พาร์เซอร์เร็วสำหรับคำสั่งวิเคราะห์ ======
_ANALYZE_TH = re.compile(
    r"^(?:วิเคราะห์|analyze)\s+([A-Za-z0-9:/._-]+)(?:\s+([0-9]+[mMhHdDwW]|[124]H|1D|4H|1W|15m|30m|60m|1ชั่วโมง|4ชั่วโมง|1วัน|1สัปดาห์))?$",
    re.IGNORECASE,
)

def _quick_parse_analyze(text: str):
    """
    รับ: "วิเคราะห์ BTC", "วิเคราะห์ BTCUSDT 4H", "analyze btc 1D", "วิเคราะห์ BTC 1ชั่วโมง"
    คืน: (symbol_norm, tf_norm) หรือ None
    ดีฟอลต์: symbol=BTCUSDT เมื่อให้ 'BTC', tf=1D เมื่อไม่ระบุ
    """
    m = _ANALYZE_TH.match(text.strip())
    if not m:
        return None
    sym_raw = m.group(1)
    tf_raw  = (m.group(2) or "").strip()
    symbol = _norm_symbol(sym_raw)
    if symbol in ("BTC", "XBT"):  # ปรับได้ตามที่ใช้จริง
        symbol = "BTCUSDT"
    tf_map = {
        "1H":"1H", "4H":"4H", "1D":"1D", "1W":"1W",
        "1ชั่วโมง":"1H", "4ชั่วโมง":"4H", "1วัน":"1D", "1สัปดาห์":"1W",
        "15M":"15m", "30M":"30m", "60M":"1H",
        "15m":"15m", "30m":"30m",
    }
    tf = tf_map.get(tf_raw.upper(), "1D") if tf_raw else "1D"
    return (symbol, tf)


# NOTE: main.py include_router(..., prefix="/line")
# ดังนั้น path ที่นี่ใช้ "/webhook" ให้ลงตัวเป็น /line/webhook
@router.post("/webhook")
async def line_webhook(request: Request):
    """
    LINE webhook entrypoint:
    - ตรวจลายเซ็นต์
    - ไล่ events และตอบตาม logic
    """
    if _parser is None or _config is None:
        raise HTTPException(status_code=500, detail="LINE credentials are not configured")

    signature = request.headers.get("x-line-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature")

    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    try:
        events = _parser.parse(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ใช้ ApiClient ต่อครั้ง (short-lived)
    with ApiClient(_config) as api_client:
        messaging_api = MessagingApi(api_client)

        for event in events:
            if not isinstance(event, MessageEvent):
                continue
            if not isinstance(event.message, TextMessageContent):
                continue

            user_text = (event.message.text or "").strip()
            user_id = getattr(event.source, "user_id", None)

            # 0.5) วิเคราะห์จริง (ดักก่อน get_reply เพื่อไม่โดนกลืน)
            parsed = _quick_parse_analyze(user_text) or parse_analyze_command(user_text)
            if parsed:
                symbol, tf = parsed
                try:
                    df = get_data(symbol, tf)
                    result = analyze_scenarios(df, symbol=symbol, tf=tf)

                    pct = result.get("percent", {}) or {}
                    lv = result.get("levels", {}) or {}
                    fib = lv.get("fibo", {}) or {}
                    el = lv.get("elliott_targets", {}) or {}

                    reply = (
                        f"🔎 วิเคราะห์ {symbol} | TF: {tf}\n"
                        f"• แนวโน้ม: UP {pct.get('up',0)}% | DOWN {pct.get('down',0)}% | SIDE {pct.get('side',0)}%\n"
                        f"• Key Levels:\n"
                        f"   - Swing High: {fmt_num(lv.get('recent_high'))}\n"
                        f"   - Swing Low : {fmt_num(lv.get('recent_low'))}\n"
                        f"   - EMA50/200: {fmt_num(lv.get('ema50'))} / {fmt_num(lv.get('ema200'))}\n"
                        f"   - Fibo 0.618 / 1.618: {fmt_num(fib.get('retr_0.618'))} / {fmt_num(fib.get('ext_1.618'))}\n"
                        + (f"   - Elliott targets: {', '.join(f'{k}:{fmt_num(v)}' for k,v in el.items())}\n" if el else "")
                    )
                except FileNotFoundError:
                    reply = "⚠️ ไม่พบไฟล์ข้อมูล: app/data/historical.xlsx"
                except ValueError as e:
                    reply = f"⚠️ ข้อมูลไม่พร้อม: {e}"
                except Exception as e:
                    reply = f"⚠️ เกิดข้อผิดพลาดระหว่างวิเคราะห์: {e}"

                _reply_text(messaging_api, event.reply_token, reply)
                continue

            # 0) ตั้ง/ยกเลิกแจ้งเตือนราคา (watch / unwatch)
            m = _WATCH_SET.match(user_text)
            if user_id and m:
                sym = _norm_symbol(m.group(1))
                entry = float(m.group(2))
                tol = float(m.group(3)) if m.group(3) else 0.0
                add_watch(user_id, sym, entry, tol)
                _reply_text(
                    messaging_api,
                    event.reply_token,
                    f"✅ ตั้งแจ้งเตือน {sym}\n• Entry: {fmt_num(entry)}\n• Tol: ±{fmt_num(tol)}",
                )
                continue

            m = _WATCH_DEL.match(user_text)
            if user_id and m:
                sym = _norm_symbol(m.group(1))
                ok = remove_watch(user_id, sym)
                _reply_text(
                    messaging_api,
                    event.reply_token,
                    f"{'🗑️ ยกเลิก' if ok else 'ℹ️ ไม่พบ'} การแจ้งเตือน {sym}",
                )
                continue

            # 1) แมพปิ้งข้อความทั่วไป
            mapped = get_reply(user_text)
            if mapped:
                _reply_text(messaging_api, event.reply_token, mapped)
                continue

            # 2) คำสั่งราคา: "ราคา BTC" / "price eth"
            symbol_price = parse_price_command(user_text)
            if symbol_price:
                price_text = await _handle_price(symbol_price)
                _reply_text(messaging_api, event.reply_token, price_text)
                continue

            # 3) คำสั่ง mock: "mock" / "วิเคราะห์ mock"
            if parse_analysis_mock(user_text):
                mock_text = (
                    "🧪 MOCK ANALYSIS\n"
                    "UP 40% | DOWN 35% | SIDE 25%\n"
                    "Key Levels:\n"
                    " - SwingH: 60,500\n - SwingL: 58,200\n"
                    " - EMA50/200: 59,800 / 57,900\n"
                    " - Fibo 0.618 / 1.618: 59,200 / 61,400\n"
                    "หมายเหตุ: ข้อมูลจำลองเพื่อทดสอบเท่านั้น"
                )
                _reply_text(messaging_api, event.reply_token, mock_text)
                continue

            # 5) ไม่เข้าเงื่อนไขใด ๆ → ส่งตัวช่วยใช้งาน
            helper = (
                "สวัสดีครับ 👋 ตัวอย่างคำสั่ง:\n"
                "• ราคา BTC\n"
                "• วิเคราะห์ BTCUSDT 1H\n"
                "• ตั้งเข้า BTCUSDT 60000 (หรือ watch btc 60000 tol=50)\n"
                "• ยกเลิกเข้า BTCUSDT (หรือ unwatch btc)\n"
                "• mock"
            )
            _reply_text(messaging_api, event.reply_token, helper)

    return PlainTextResponse("OK")


def _norm_symbol(s: str) -> str:
    return s.upper().replace(":", "").replace("/", "")


def _reply_text(api: MessagingApi, reply_token: str, text: str) -> None:
    # กันข้อความยาวเกิน 5000
    if text and len(text) > 4900:
        text = text[:4900] + "\n[truncated]"
    api.reply_message(
        ReplyMessageRequest(
            replyToken=reply_token,
            messages=[LineTextMessage(text=text)],
        )
    )


async def _handle_price(symbol: str) -> str:
    """
    ดึงราคาแบบยืดหยุ่น:
    - ถ้า project มี provider → เรียกใช้
    - ถ้าล้มเหลว → แจ้งเตือนผู้ใช้
    """
    try:
        from app.adapters.price_provider import get_price  # type: ignore
        px = await _maybe_async(get_price, symbol)
        if px is not None:
            return f"📈 {symbol}\nราคา: {fmt_num(px)}"
    except Exception:
        pass
    return f"⚠️ ยังไม่พร้อมดึงราคา {symbol} (โปรดตรวจสอบ PRICE_PROVIDER หรือ provider function)."


async def _maybe_async(func, *args, **kwargs):
    """รองรับทั้งฟังก์ชัน sync/async โดยไม่ต้องรู้ล่วงหน้า"""
    import inspect
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return func(*args, **kwargs)


def fmt_num(val) -> str:
    """ฟอร์แมตตัวเลขอ่านง่าย"""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return "-"
    if abs(x) >= 1000:
        return f"{x:,.2f}"
    if abs(x) >= 1:
        return f"{x:.4f}"
    return f"{x:.6f}"
