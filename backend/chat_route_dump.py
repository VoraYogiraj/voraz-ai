import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from services.session_service import create_session
from agents.orchestrator import run_turn
from agents.image_intake import process_photo

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    session_token: Optional[str] = None
    message: str
    avatar_type: Optional[str] = None


class ChatResponse(BaseModel):
    session_token: str
    reply: str
    stage: Optional[str] = None


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

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
    None, run_turn, token, request.message, None, request.avatar_type
)
        return ChatResponse(
            session_token=token,
            reply=result["reply"],
            stage=result.get("stage"),
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Something went wrong, please try again.")


@router.post("/chat/photo")
async def chat_photo_endpoint(
    session_token: str = Form(...),
    consent_given: bool = Form(...),
    photo: UploadFile = File(...),
):
    if not consent_given:
        raise HTTPException(status_code=400, detail="Photo upload requires consent.")

    try:
        image_bytes = await photo.read()
        file_ext = (photo.filename or "jpg").rsplit(".", 1)[-1].lower()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, process_photo, session_token, image_bytes, consent_given, None, file_ext
        )
        return result

    except Exception as e:
        logger.error(f"Photo intake error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Something went wrong processing the photo.")
