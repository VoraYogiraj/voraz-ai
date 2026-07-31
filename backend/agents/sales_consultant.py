"""
backend/agents/sales_consultant.py

Phase C / item 15 of the VORA agent build plan.
Scope (current): consultation booking only.
Upsell/cross-sell via product_customization_map + conversion_rules.json
is deferred until real SKU eligibility data exists.

Responsibilities:
  - Detect when the conversation is ready to offer a consultation
  - Collect contact info (name, phone/email) and optional preferred slot
    from the user message via LLM extraction
  - Write a row to consultation_bookings
  - Return a confirmation reply for the orchestrator to send back

FK chain (same as photo_uploads):
  consultation_bookings.session_id → conversations.session_id
  conversations.session_id → customer_profiles.session_id
  So a valid session must exist before book_consultation() is called.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from openai import OpenAI

from config import settings
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

supabase = get_supabase()

client = OpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
)


# ── Trigger detection ─────────────────────────────────────────────────────────

CONSULTATION_TRIGGERS = [
    "book", "appointment", "consult", "meet", "visit", "come in",
    "schedule", "slot", "available", "when can i", "can i come",
    "in person", "showroom", "trial", "fitting",
]


def should_offer_consultation(user_message: str) -> bool:
    """
    Lightweight keyword check — returns True if the user message looks like
    a consultation request. Called by the orchestrator before running the
    full LLM extraction to avoid unnecessary API calls.
    """
    msg = user_message.lower()
    return any(trigger in msg for trigger in CONSULTATION_TRIGGERS)


# ── Contact info extraction ───────────────────────────────────────────────────

def _extract_contact_info(user_message: str, session_id: str) -> dict[str, Any]:
    """
    Asks GPT-4o-mini to pull name, phone, email, and preferred_slot out of
    the user message. Returns whatever it finds — missing fields are None,
    not an error. Caller decides whether to prompt for missing required fields.
    """
    prompt = f"""Extract contact information from the following message for a bridal consultation booking.

Return ONLY a JSON object, no preamble, no markdown fences:
{{
  "name": "<full name or null>",
  "phone": "<phone number as string or null>",
  "email": "<email address or null>",
  "preferred_slot": "<date/time string if mentioned, or null>"
}}

Message: {user_message}
"""
    try:
        response = client.chat.completions.create(
            model=settings.openrouter_model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Contact extraction failed for session {session_id}: {e}", exc_info=True)
        return {"name": None, "phone": None, "email": None, "preferred_slot": None}


# ── Booking ───────────────────────────────────────────────────────────────────

def book_consultation(
    session_id: str,
    user_message: str,
    customer_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Main entry point. Extracts contact info from user_message, writes a
    consultation_bookings row, returns a reply string + the extracted data.

    Return shape:
    {
        "reply": "<confirmation message to send back to the user>",
        "booking_id": <int or None if insert failed>,
        "contact_info": { "name": ..., "phone": ..., "email": ... },
        "missing_fields": ["phone"]   # list of required fields not found
    }

    Missing required fields (name + at least one of phone/email):
      - booking is NOT written to DB
      - reply asks the user to provide the missing info
      - missing_fields lists what's needed so the orchestrator can re-prompt

    preferred_slot is optional — booked as None if not mentioned.
    """
    extracted = _extract_contact_info(user_message, session_id)

    name = extracted.get("name")
    phone = extracted.get("phone")
    email = extracted.get("email")
    preferred_slot_raw = extracted.get("preferred_slot")

    # Determine missing required fields
    missing = []
    if not name:
        missing.append("name")
    if not phone and not email:
        missing.append("phone or email")

    if missing:
        missing_str = " and ".join(missing)
        return {
            "reply": (
                f"I'd love to book a consultation for you! "
                f"Could you share your {missing_str} so we can confirm your appointment?"
            ),
            "booking_id": None,
            "contact_info": extracted,
            "missing_fields": missing,
        }

    # Parse preferred_slot if provided
    preferred_slot = None
    if preferred_slot_raw:
        try:
            from dateutil import parser as dateparser
            preferred_slot = dateparser.parse(preferred_slot_raw).isoformat()
        except Exception:
            logger.warning(f"Could not parse preferred_slot '{preferred_slot_raw}' — storing as None")

    contact_info = {k: v for k, v in {"name": name, "phone": phone, "email": email}.items() if v}

    now = datetime.now(timezone.utc)
    payload = {
        "session_id": session_id,
        "contact_info": contact_info,
        "preferred_slot": preferred_slot,
        "status": "pending",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    if customer_id:
        payload["customer_id"] = customer_id

    booking_id = None
    try:
        result = supabase.table("consultation_bookings").insert(payload).execute()
        if result.data:
            booking_id = result.data[0].get("id")
            logger.info(f"Consultation booked: id={booking_id} session={session_id}")
    except Exception as e:
        logger.error(f"Failed to write consultation_bookings for session {session_id}: {e}", exc_info=True)

    slot_str = f" for {preferred_slot_raw}" if preferred_slot_raw else ""
    reply = (
        f"Your consultation has been booked{slot_str}! ✨ "
        f"Our team will reach out to {phone or email} shortly to confirm your appointment. "
        f"We look forward to meeting you, {name}!"
    )

    return {
        "reply": reply,
        "booking_id": booking_id,
        "contact_info": contact_info,
        "missing_fields": [],
    }