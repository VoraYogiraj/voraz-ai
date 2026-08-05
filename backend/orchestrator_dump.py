"""
backend/agents/orchestrator.py

Phase C / item 16 of the VORA agent build plan.
State machine tying all 6 VORA stages together per turn.

Stages (in order):
  1. greeting     — first turn, warm welcome, bootstrap session
  2. profiling    — slot-filling via run_profiler_turn until profile complete
  3. objection    — runs every turn from profiling onward, short-circuits if matched
  4. styling      — run_stylist_agent once profile is sufficiently filled
  5. consulting   — offer/complete consultation booking
  6. done         — session complete, no further processing needed

Stage flow per turn:
  - Objection check runs BEFORE the stage-specific handler (stages 2–5)
  - If objection matched → return resolution reply, stay in current stage
  - Otherwise → run the stage handler, advance stage when ready

Profile completeness threshold (move profiling → styling):
  At least 3 of 5 core slots filled: budget, timeline, event_type,
  style_prefs, location. This matches the "soft gate" approach used
  elsewhere — we don't block on a perfect profile, we recommend with
  what we have and keep filling in the background.

intent_classifier is intentionally NOT called at module level here
because it has a known bug (ChatOpenAI initialized without API key at
import time). It is imported inside the function that needs it so the
rest of the orchestrator remains importable even if that file is broken.
"""

import logging
from typing import Any, Optional

from agents.memory_store import (
    bootstrap_session,
    get_history,
    set_stage,
    add_message,
    get_or_create_profile,
)
from agents.profiler import run_profiler_turn
from agents.objection_handler import handle_objection
from agents.sales_consultant import should_offer_consultation, book_consultation
from agents.stylist_agent import run_stylist_agent

logger = logging.getLogger(__name__)

# Stages in progression order — used for comparisons
STAGE_ORDER = ["greeting", "profiling", "styling", "consulting", "done"]

# Minimum filled slots before moving profiling → styling
PROFILE_SLOTS_REQUIRED = ["budget_min", "event_type", "style_prefs"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _current_stage(session_id: str) -> str:
    """Read current_stage directly from the conversations row."""
    from agents.memory_store import get_or_create_conversation
    convo = get_or_create_conversation(session_id)
    return convo.get("current_stage") or "greeting"


def _profile_ready(profile: dict) -> bool:
    """True if enough slots are filled to move to styling."""
    filled = sum(
        1 for slot in PROFILE_SLOTS_REQUIRED
        if profile.get(slot) not in (None, "", [], {})
    )
    return filled >= 2  # at least 2 of 3 required slots


def _advance_stage(session_id: str, current: str, target: str) -> None:
    """Move session to target stage only if it's actually an advancement."""
    if STAGE_ORDER.index(target) > STAGE_ORDER.index(current):
        set_stage(session_id, target)
        logger.info(f"Session {session_id}: {current} → {target}")


# ── Stage handlers ────────────────────────────────────────────────────────────

def _handle_greeting(session_id: str, message: str, profile: dict) -> str:
    """First turn — warm welcome, classify intent, move to profiling."""
    from agents.intent_classifier import classify_intent
    from agents.memory_store import update_profile

    try:
        avatar_type = classify_intent(message)
        update_profile(session_id, {"avatar_type": avatar_type})
    except Exception as e:
        logger.warning(f"Intent classification failed (non-fatal): {e}")

    _advance_stage(session_id, "greeting", "profiling")
    return (
        "Welcome to VORAZ! ✨ I'm VORA, your personal bridal stylist. "
        "I'm here to help you find your dream look — whether you're looking for something "
        "ready to wear, custom-made, or completely bespoke. "
        "Tell me a little about yourself — what's the occasion and when is your big day?"
    )

def _handle_profiling(session_id: str, message: str, profile: dict, customer_id: Optional[str]) -> str:
    """Slot-fill until profile is ready, then advance to styling."""
    result = run_profiler_turn(session_id, message, customer_id)
    missing = result.get("missing_slots", [])
    updated_profile = result.get("profile", profile)

    avatar_type = updated_profile.get("avatar_type")
    if avatar_type not in ("custom", "bespoke"):
        missing = [s for s in missing if s != "wedding_date"]

    if _profile_ready(updated_profile):
        _advance_stage(session_id, "profiling", "styling")
        return (
            "Perfect, I've got a good sense of what you're looking for! "
            "Let me pull together some options for you. ✨"
        )

    if not missing:
        return "Tell me more about what you're looking for!"

    next_slot = missing[0]
    prompts = {
        "budget_min": "What budget range did you have in mind for your outfit?",
        "wedding_date": "When's the big day? That'll help me guide you on timelines.",
        "event_type": "Is this for the wedding ceremony, sangeet, reception, or another function?",
        "location": "Which city will the wedding be in?",
        "style_prefs": "What's your dream look — any colors, silhouettes, or vibes in mind?",
    }
    return prompts.get(next_slot, "Tell me a bit more so I can find your perfect look!")

def _handle_styling(session_id: str, message: str, profile: dict) -> str:
    """Run stylist agent with full chat history."""
    history = get_history(session_id, limit=20)
    chat_history = [
        {"role": m["role"], "content": m["content"]}
        for m in history
    ]
    reply = run_stylist_agent(message, chat_history, session_id=session_id)

    # After styling, check if user wants to book — advance if so
    if should_offer_consultation(message):
        _advance_stage(session_id, "styling", "consulting")

    return reply


def _handle_consulting(session_id: str, message: str, customer_id: Optional[str]) -> str:
    """Attempt to book consultation from current message."""
    result = book_consultation(session_id, message, customer_id)

    if not result["missing_fields"]:
        # Booking complete
        _advance_stage(session_id, "consulting", "done")

    return result["reply"]


# ── Main entry point ──────────────────────────────────────────────────────────

def run_turn(
    session_id: str,
    message: str,
    customer_id: Optional[str] = None,
    avatar_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Process one user turn. Called by chat.py / webhook.py instead of
    calling run_stylist_agent directly.

    Returns:
    {
        "reply": str,           # text to send back to the user
        "stage": str,           # stage the session is in AFTER this turn
        "session_id": str,
    }
    """
    # 1. Bootstrap session (idempotent â€" safe to call every turn)
    bootstrap_session(session_id, customer_id)
    # 1b. If frontend explicitly passed avatar_type, seed the profile immediately
    if avatar_type and avatar_type not in ("unclear", ""):
        update_profile(session_id, {"avatar_type": avatar_type})
    # 2. Persist user message
    add_message(session_id, "user", message)
    # 3. Get current profile + stage
    profile = get_or_create_profile(session_id, customer_id)

    # 4. Objection check — runs on every turn except greeting
    if stage != "greeting":
        objection = handle_objection(message, session_id)
        if objection:
            reply = objection.get("resolution", "Let me help you with that.")
            add_message(session_id, "assistant", reply)
            return {"reply": reply, "stage": stage, "session_id": session_id}

    # 5. Consultation trigger check — can fire from styling stage onward
    if stage == "styling" and should_offer_consultation(message):
        _advance_stage(session_id, "styling", "consulting")
        stage = "consulting"

    # 6. Stage handler
    try:
        if stage == "greeting":
            reply = _handle_greeting(session_id, message, profile)
        elif stage == "profiling":
            reply = _handle_profiling(session_id, message, profile, customer_id)
        elif stage == "styling":
            reply = _handle_styling(session_id, message, profile)
        elif stage == "consulting":
            reply = _handle_consulting(session_id, message, customer_id)
        elif stage == "done":
            reply = (
                "Your consultation is all set! 🌸 Our team will be in touch soon. "
                "Is there anything else I can help you with in the meantime?"
            )
        else:
            logger.warning(f"Unknown stage '{stage}' for session {session_id} — defaulting to profiling")
            reply = _handle_profiling(session_id, message, profile, customer_id)
    except Exception as e:
        logger.error(f"Stage handler '{stage}' failed for session {session_id}: {e}", exc_info=True)
        reply = "I'm sorry, something went wrong on my end. Could you repeat that?"

    # 7. Persist assistant reply
    add_message(session_id, "assistant", reply)

    # 8. Re-read stage after potential advancement
    final_profile = get_or_create_profile(session_id, customer_id)
    final_stage = _current_stage(session_id)

    return {"reply": reply, "stage": final_stage, "session_id": session_id}
