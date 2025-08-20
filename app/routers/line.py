from fastapi import APIRouter

router = APIRouter()

@router.post("/webhook")
async def webhook():
    return {"message": "line webhook"}
