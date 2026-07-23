# backend/routes/quiz.py
import json
import logging
import os
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.session_service import create_session, get_session
from services.supabase_client import supabase
from tools.quiz_filter_tool import filter_products
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "quiz_config.json")

with open(CONFIG_PATH, "r") as f:
    QUIZ_CONFIG = json.load(f)


class AnswerRequest(BaseModel):
    session_token: Optional[str] = None
    question_id: str
    value: Any  # str for single_select, list for multi_select, dict for lead_form


class AnswerResponse(BaseModel):
    session_token: str
    quiz_step: str


class ResultsRequest(BaseModel):
    session_token: str


@router.get("/quiz/questions")
async def get_quiz_questions():
    """Static question/branching config for the quiz engine (vora-quiz.js)."""
    return QUIZ_CONFIG


@router.get("/quiz/resume/{session_token}")
async def resume_quiz(session_token: str):
    """Fetch saved answers + last step so vora-quiz.js can restore state."""
    session = get_session(session_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_token": session_token,
        "quiz_answers": session.get("quiz_answers", {}),
        "quiz_step": session.get("quiz_step"),
        "quiz_completed": session.get("quiz_completed", False),
    }


@router.post("/quiz/answer", response_model=AnswerResponse)
async def save_quiz_answer(request: AnswerRequest):
    """Persist one answer + current step, for resumability. Called after every chip tap."""
    token = request.session_token
    if not token:
        session = create_session()
        if not session:
            raise HTTPException(status_code=500, detail="Could not create session")
        token = session["session_token"]

    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    quiz_answers = session.get("quiz_answers", {}) or {}
    quiz_answers[request.question_id] = request.value

    try:
        supabase.table("chat_sessions").update({
            "quiz_answers": quiz_answers,
            "quiz_step": request.question_id,
        }).eq("session_token", token).execute()
    except Exception as e:
        logger.error(f"Failed saving quiz answer: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not save answer")

    return AnswerResponse(session_token=token, quiz_step=request.question_id)


def _save_lead(answers: Dict[str, Any], order_type: Optional[str]) -> None:
    lead = answers.get("lead_capture") or {}
    if not lead:
        return
    try:
        supabase.table("customer_profiles").upsert({
            "whatsapp_number": lead.get("whatsapp_number"),
            "name": lead.get("name"),
            "city": lead.get("city"),
            "inspiration_image_url": lead.get("inspiration", {}).get("image_url") if isinstance(lead.get("inspiration"), dict) else None,
            "inspiration_link": lead.get("inspiration", {}).get("url") if isinstance(lead.get("inspiration"), dict) else None,
            "lead_source": f"quiz_{order_type}" if order_type else "quiz",
            "lead_captured_at": "now()",
        }, on_conflict="whatsapp_number").execute()
    except Exception as e:
        logger.error(f"Failed saving lead: {e}", exc_info=True)


@router.post("/quiz/results")
async def get_quiz_results(request: ResultsRequest):
    """Final step: reads saved answers for the session, saves the lead, and either
    runs the hard-filter product query (Ready to Ship / Choose & Customize) or
    returns a stylist handoff payload (Fully Bespoke — no product query)."""
    session = get_session(request.session_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = session.get("quiz_answers", {}) or {}
    order_type = answers.get("order_type")
    if not order_type:
        raise HTTPException(status_code=400, detail="order_type not answered yet")

    _save_lead(answers, order_type)

    cta_config = QUIZ_CONFIG["questions"][-1]["cta_by_order_type"].get(order_type, {})
    stylist_number = os.environ.get("WHATSAPP_STYLIST_NUMBER", "")  # display number for wa.me handoff link

    try:
        supabase.table("chat_sessions").update({
            "quiz_completed": True,
        }).eq("session_token", request.session_token).execute()
    except Exception as e:
        logger.error(f"Failed marking quiz complete: {e}", exc_info=True)

    if order_type == "fully_bespoke":
        return {
            "order_type": order_type,
            "products": [],
            "loosened": [],
            "cta": {**cta_config, "whatsapp_link": f"https://wa.me/{stylist_number}" if stylist_number else None},
        }

    result = filter_products(
        occasion=answers.get("occasion"),
        order_type=order_type,
        silhouette=answers.get("silhouette"),
        fit_type=answers.get("fit_type"),
        vibe=answers.get("vibe"),
        color=answers.get("color"),
        match_count=12,
    )

    return {
        "order_type": order_type,
        "products": result["products"],
        "loosened": result["loosened"],
        "cta": {**cta_config, "whatsapp_link": f"https://wa.me/{stylist_number}" if stylist_number else None},
    }


@router.get("/quiz/prefill/{shopify_product_id}")
async def prefill_from_product(shopify_product_id: str):
    """For the product-page quiz embed: pre-fills quiz answers from that product's
    own metafield values as a starting point."""
    try:
        result = supabase.table("products").select(
            "occasion, vibe, silhouette, fit_type, order_type, color_palette"
        ).eq("shopify_product_id", shopify_product_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        p = result.data
        return {
            "order_type": p.get("order_type"),
            "occasion": p.get("occasion"),
            "vibe": p.get("vibe") or [],
            "silhouette": p.get("silhouette"),
            "fit_type": p.get("fit_type"),
            "color": (p.get("color_palette") or [None])[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prefill error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not load product for prefill")