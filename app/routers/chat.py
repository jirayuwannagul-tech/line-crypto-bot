from fastapi import APIRouter
from app.schemas.chat_io import ChatRequest, ChatResponse
from app.services.chat_service import simple_reply
router = APIRouter()
@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return simple_reply(req)
