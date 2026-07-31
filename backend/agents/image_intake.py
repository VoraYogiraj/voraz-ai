"""
backend/agent/image_intake.py

Phase C / item 14 of the VORA agent build plan.
Optional, opt-in photo-based matching. Produces the SAME color/silhouette
slot values the text-based Profiler/Stylist flow already produces — just
from a photo instead of an answer. Output is always a SOFT ranking signal,
never a hard filter, consumed by stylist.py.

Decisions locked in:
  - Detection via LLM vision call (GPT-4o-mini through the existing
    OpenRouter client) — reuses the same auth/billing/pattern as
    intent_classifier.py and profiler.py. No new vendor, no local model.
  - Vocabulary is the real color/silhouette option lists from
    quiz_config.json — the model must pick from known values, not invent
    new ones, so downstream filtering stays consistent with the text flow.
  - Consent is mandatory and checked BEFORE any image is sent anywhere.
    No consent → no processing, full stop.
  - Photo bytes are stored in Supabase Storage bucket 'customer-photos'
    (private, confirmed created); photo_uploads table stores only the
    storage path + results, never raw bytes.
  - 30-day retention: delete_after is set at insert time. Actual deletion
    enforcement (scheduled job) is a separate item, not built here.
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
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

RETENTION_DAYS = 30
STORAGE_BUCKET = "customer-photos"

# Vocabulary sourced directly from quiz_config.json's "color" and
# "silhouette" question options — kept in sync with the text-based quiz
# flow per the "reuse, don't rebuild" rule.
VALID_COLORS = [
    "Red", "Blush Pink", "Ivory", "Gold", "Purple", "Sage Green", "Blue",
    "Yellow", "Maroon", "Rani Pink", "Magenta", "Wine", "Emerald", "Teal",
    "Peach", "Blush", "Champagne", "Coral", "Mint", "Navy", "Black",
    "White", "Beige", "Mustard", "Rust", "Silver", "Lavender", "Grey", "Orange",
]

VALID_SILHOUETTES = [
    "Lehenga", "A-Line Flared Lehenga", "Straight/Column", "Anarkali",
    "Mermaid", "Sharara", "Gown", "Cape Style", "Jacket-Style Lehenga",
]


class ConsentNotGivenError(Exception):
    """Raised when image processing is attempted without consent on file."""
    pass


def _upload_photo(session_id: str, image_bytes: bytes, file_ext: str = "jpg") -> str:
    """Uploads raw image bytes to Supabase Storage, returns the storage path.
    Never stores raw bytes in the DB — only this path goes in photo_uploads."""
    storage_path = f"{session_id}/{datetime.now(timezone.utc).timestamp()}.{file_ext}"
    supabase.storage.from_(STORAGE_BUCKET).upload(
        storage_path, image_bytes, {"content-type": f"image/{file_ext}"}
    )
    return storage_path


def _build_vision_prompt() -> str:
    return f"""You are analyzing a photo for soft styling signals only — never for identity, never for any purpose beyond color and silhouette matching for bridal wear recommendations.

Return ONLY a JSON object, no preamble, no markdown fences, in this exact shape:
{{
  "undertone_colors": [<1-3 values from {VALID_COLORS}>],
  "body_shape_silhouettes": [<1-3 values from {VALID_SILHOUETTES}>],
  "confidence": "low" | "medium" | "high"
}}

Rules:
- undertone_colors: which colors from the list would suit this person's skin undertone. Pick colors that flatter, not colors present in the photo.
- body_shape_silhouettes: which silhouettes from the list tend to suit the general body shape visible. If the photo angle, pose, or clothing makes this unclear, set confidence to "low" and still give your best 1-2 guesses — never leave the array empty.
- Use ONLY values from the provided lists, matching spelling/casing exactly. Do not invent new values.
- confidence should be "low" if the photo is unclear, partial, poorly lit, or the body shape is obscured by clothing/pose/angle.
"""


def _run_vision_call(image_bytes: bytes) -> dict[str, Any]:
    """Sends the image to GPT-4o-mini via OpenRouter, returns parsed JSON.
    Raises on malformed response — caller should handle gracefully since
    this is a soft signal, not a required step."""
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=settings.openrouter_model_id,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_vision_prompt()},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                    },
                ],
            }
        ],
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def process_photo(
    session_id: str,
    image_bytes: bytes,
    consent_given: bool,
    customer_id: Optional[str] = None,
    file_ext: str = "jpg",
) -> dict[str, Any]:
    """Main entry point. Requires explicit consent_given=True from the caller
    (the caller is responsible for having shown consent copy and captured
    the user's choice before this is ever invoked — this function does not
    show UI, it only enforces the gate).

    Returns a dict of soft signals for stylist.py to consume:
      {
        "undertone_colors": [...],
        "body_shape_silhouettes": [...],
        "confidence": "low"|"medium"|"high",
      }

    Raises ConsentNotGivenError if consent_given is False — this is a hard
    stop, not a soft failure, since processing without consent is a
    privacy violation regardless of downstream use.
    """
    if not consent_given:
        raise ConsentNotGivenError(
            "process_photo called without consent_given=True — refusing to process image."
        )

    storage_path = _upload_photo(session_id, image_bytes, file_ext)

    now = datetime.now(timezone.utc)
    delete_after = now + timedelta(days=RETENTION_DAYS)

    try:
        vision_result = _run_vision_call(image_bytes)
        undertone = vision_result.get("undertone_colors", [])
        body_shape = vision_result.get("body_shape_silhouettes", [])
        confidence = vision_result.get("confidence", "low")
    except Exception as e:
        logger.error(f"Vision call failed for session {session_id}: {e}", exc_info=True)
        undertone, body_shape, confidence = [], [], "low"

    payload = {
        "session_id": session_id,
        "image_ref": storage_path,
        "undertone_result": undertone,
        "body_shape_result": body_shape,
        "consent_given": True,
        "consent_timestamp": now.isoformat(),
        "delete_after": delete_after.isoformat(),
    }
    if customer_id:
        payload["customer_id"] = customer_id

    try:
        supabase.table("photo_uploads").insert(payload).execute()
    except Exception as e:
        logger.error(f"Failed to write photo_uploads row for session {session_id}: {e}", exc_info=True)

    return {
        "undertone_colors": undertone,
        "body_shape_silhouettes": body_shape,
        "confidence": confidence,
    }