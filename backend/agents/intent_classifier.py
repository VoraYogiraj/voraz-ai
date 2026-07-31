"""
backend/agent/intent_classifier.py

Phase C / item 10 of the VORA agent build plan.
Single Ready/Custom/Bespoke classification — replaces the old separate
"avatar detection" + "intent detection" steps, since they were the same
underlying signal (per the build plan's gap analysis).

Decisions locked in:
  - Uses GPT-4o-mini directly (matching the rest of the stack, per
    memory notes on the model migration away from OpenRouter).
  - Returns a strict enum string, never free text, so orchestrator.py
    can pattern-match on the result safely.
  - Falls back to "unclear" rather than guessing, so profiler.py knows
    to ask a direct clarifying question instead of silently assuming
    Ready to Ship (the cheapest/most common option) and under-selling.
  - Classification writes straight to customer_profiles.avatar_type via
    memory_store.update_profile — orchestrator.py doesn't have to.
"""
from config import settings
from typing import Literal

from langchain_openai import ChatOpenAI

from agents import memory_store

AvatarType = Literal["ready", "custom", "bespoke", "unclear"]

_SYSTEM_PROMPT = """You classify a bride's message into exactly one of these
categories based on what she's looking for:

- "ready": She wants something she can see and buy as-is, off the shelf,
  no changes to fit/fabric/design. Signals: "do you have this in stock",
  "can I get this now", "ready made", "off the rack".
- "custom": She wants to modify an existing design — different fabric,
  color, size, minor design tweaks to something that already exists.
  Signals: "can you change the color", "different fabric", "make it in
  my size", "customize this".
- "bespoke": She wants something designed from scratch around her own
  vision, not based on an existing product. Signals: "design something
  unique for me", "nothing like what I've seen", "one of a kind",
  describing a vision with no reference product.
- "unclear": The message doesn't give enough signal to tell yet.

Respond with exactly one word: ready, custom, bespoke, or unclear.
No punctuation, no explanation."""

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=settings.openrouter_api_key)


def classify_intent(message: str) -> AvatarType:
    """Classify a single user message into an avatar_type. Call this once
    enough context exists (don't force it on message 1 if she hasn't
    said anything intent-bearing yet — profiler.py decides when to call)."""
    response = _llm.invoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
    )
    result = response.content.strip().lower()
    if result not in ("ready", "custom", "bespoke", "unclear"):
        return "unclear"
    return result  # type: ignore[return-value]


def classify_and_store(session_id: str, message: str) -> AvatarType:
    """Classify intent and persist it to customer_profiles.avatar_type in
    one call, unless the result is 'unclear' — we don't want to overwrite
    a previously-confirmed avatar_type with a guess."""
    result = classify_intent(message)
    if result != "unclear":
        memory_store.update_profile(session_id, {"avatar_type": result})
    return result
