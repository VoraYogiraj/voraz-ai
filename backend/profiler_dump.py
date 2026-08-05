"""
backend/agent/profiler.py

Phase C / item 11 of the VORA agent build plan.
Customer Profiler stage — slot-fills budget, timeline, event, style, and
location from free-text user messages, merging into the existing
customer_profiles row rather than overwriting it wholesale.

Decisions locked in:
  - Reads/writes only through memory_store.py (get_or_create_profile,
    update_profile) — never touches Supabase directly, per the
    one-file-owns-table-access rule from memory_store.py's docstring.
  - Never overwrites a slot the customer already gave with a null/lower-
    confidence guess — merge is additive, not destructive.
  - Returns which slots are still missing so orchestrator.py can decide
    whether to keep asking or move to the next stage.
  - Uses a single structured-JSON LLM call per turn rather than five
    separate slot-specific calls, to keep latency and cost down.
"""

import json
import logging
from typing import Any, Optional

from openai import OpenAI

from agents.memory_store import get_or_create_profile, update_profile
from config import settings

logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)

# Slots this stage is responsible for filling on customer_profiles.
PROFILE_SLOTS = ["budget_min", "budget_max", "wedding_date", "event_type", "style_prefs", "location"]

EXTRACTION_SYSTEM_PROMPT = """You are extracting bridal-shopping profile details from a customer's message.

Return ONLY a JSON object (no markdown, no preamble) with these keys, all optional —
omit a key entirely if the message gives no signal for it:

- budget_min: integer (lower bound of budget, in the currency the user implies, no symbols)
- budget_max: integer (upper bound of budget). If the customer gives only one number (e.g. "50,000",
  "my budget is 50k"), treat it as a ceiling — set budget_max to that number only. Do NOT set
  budget_min in this case; leave it out of the JSON entirely unless the customer clearly states
  a lower bound too (e.g. "between 30k and 50k").
- wedding_date: string, ISO format YYYY-MM-DD if a specific date is given, otherwise a
  loose phrase like "next spring" or "December 2026" if that's all that's mentioned
- event_type: string, one of "wedding ceremony", "reception", "sangeet", "engagement", or another
  function name if stated. Treat ungrammatical short answers as complete, settled answers, not
  truncated fragments — a customer replying tersely to a direct question is answering, not trailing
  off. Map confidently: the literal reply "for wedding" (even without "the") means "wedding ceremony".
  Also map "wedding", "it's the wedding", "the wedding day" the same way. Don't withhold this field
  just because the phrasing is brief — a short answer to a direct question about the event is
  still a clear signal.
- style_prefs: array of short strings describing vibe/silhouette/color/garment-type words mentioned
  (e.g. ["pastel", "A-line", "minimal embroidery", "lehenga"])
- location: string, city/region if mentioned

Only extract what the message actually states or clearly implies. Do not guess or invent
values. If nothing in the message is relevant to any slot, return {}.
"""


def _extract_slots_from_message(message: str) -> dict[str, Any]:
    """Single LLM call: free text -> partial slot dict. Never raises on a
    parse failure — logs and returns {} so profiling degrades gracefully
    instead of breaking the turn."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"profiler slot extraction failed: {e}")
        return {}


def _merge_style_prefs(existing: Optional[list], new: Optional[list]) -> list:
    """style_prefs is additive — new vibe words extend the list, don't replace it."""
    existing = existing or []
    new = new or []
    merged = list(existing)
    for item in new:
        if item not in merged:
            merged.append(item)
    return merged


def run_profiler_turn(session_id: str, message: str, customer_id: Optional[str] = None) -> dict[str, Any]:
    """Main entry point called by orchestrator.py during the profiler stage.

    Extracts whatever slots the message contains, merges them into the
    existing customer_profiles row (never overwriting a filled slot with
    nothing), and returns the updated profile plus a list of still-missing
    slots so the orchestrator can decide whether to keep profiling or
    advance to problem_solver / stylist.
    """
    profile = get_or_create_profile(session_id, customer_id)
    extracted = _extract_slots_from_message(message)

    if not extracted:
        missing = [s for s in PROFILE_SLOTS if not profile.get(s)]
        return {"profile": profile, "missing_slots": missing, "updated": False}

    update_fields: dict[str, Any] = {}

    if "budget_min" in extracted or "budget_max" in extracted:
        update_fields["budget_min"] = extracted.get("budget_min", profile.get("budget_min"))
        update_fields["budget_max"] = extracted.get("budget_max", profile.get("budget_max"))

    if extracted.get("wedding_date"):
        update_fields["wedding_date"] = extracted["wedding_date"]

    if extracted.get("event_type"):
        update_fields["event_type"] = extracted["event_type"]

    if extracted.get("location"):
        update_fields["location"] = extracted["location"]

    if extracted.get("style_prefs"):
        update_fields["style_prefs"] = _merge_style_prefs(
            profile.get("style_prefs"), extracted["style_prefs"]
        )

    if not update_fields:
        missing = [s for s in PROFILE_SLOTS if not profile.get(s)]
        return {"profile": profile, "missing_slots": missing, "updated": False}

    updated_profile = update_profile(session_id, update_fields)
    missing = [s for s in PROFILE_SLOTS if not updated_profile.get(s)]

    return {"profile": updated_profile, "missing_slots": missing, "updated": True}
