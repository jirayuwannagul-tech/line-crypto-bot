from app.schemas.chat_io import ChatRequest, ChatResponse
def simple_reply(req: ChatRequest) -> ChatResponse:
    text = (req.text or "").strip()
    if not text:
        return ChatResponse(reply="พิมพ์อะไรก็ได้ เดี๋ยวฉันตอบกลับ 😊")
    return ChatResponse(reply=f"คุณว่า: {text}")
