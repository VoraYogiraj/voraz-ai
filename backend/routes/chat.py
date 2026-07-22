import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.session_service import create_session, append_message, get_session_history_for_langchain
from agents.stylist_agent import run_stylist_agent

logger = logging.getLogger(__name__)
router = APIRouter()

class ChatRequest(BaseModel):
    session_token: Optional[str] = None
    message: str

class ChatResponse(BaseModel):
    session_token: str
    reply: str

@router.post("/session")
async def start_session():
    session = create_session()
    if not session:
        raise HTTPException(status_code=500, detail="Could not create session")
    return {"session_token": session["session_token"]}

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    token = request.session_token
    if not token:
        session = create_session()
        if not session:
            raise HTTPException(status_code=500, detail="Could not create session")
        token = session["session_token"]

    history = get_session_history_for_langchain(token)
    append_message(token, "user", request.message)

    try:
        loop = asyncio.get_event_loop()
        reply = await loop.run_in_executor(None, run_stylist_agent, request.message, history)
        append_message(token, "assistant", reply)
        return ChatResponse(session_token=token, reply=reply)

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Something went wrong, please try again.")