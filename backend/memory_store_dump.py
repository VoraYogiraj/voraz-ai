"""
backend/agent/memory_store.py

Phase C / item 9 of the VORA agent build plan.
Foundation module — every other agent module (profiler, objection_handler,
stylist, sales_consultant, orchestrator) reads/writes through this file
rather than calling Supabase directly. Keeps table access in one place.

Decisions locked in:
  - Uses the existing backend/services/supabase_client.py singleton
    (get_supabase_client) rather than creating a new connection here.
  - Every function takes session_id as the primary key, matching the
    schema decisions made in the migrations (customer_profiles.session_id,
    conversations.session_id).
  - "get or create" pattern for profile/conversation, since the very
    first message in a brand-new session won't have rows yet.
  - Returns plain dicts (not custom classes) so this stays easy to drop
    into any LangChain tool/agent step without extra serialization.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from services.supabase_client import get_supabase

supabase = get_supabase()


# ---------------------------------------------------------------------------
# customer_profiles
# ---------------------------------------------------------------------------

def get_or_create_profile(session_id: str, customer_id: Optional[str] = None) -> dict[str, Any]:
    """Fetch the customer_profiles row for this session, creating it if new."""
    result = (
        supabase.table("customer_profiles")
        .select("*")
        .eq("session_id", session_id)
        .execute()
    )
    if result.data:
        return result.data[0]

    insert_payload = {"session_id": session_id}
    if customer_id:
        insert_payload["customer_id"] = customer_id

    created = supabase.table("customer_profiles").insert(insert_payload).execute()
    return created.data[0]


def update_profile(session_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Patch specific fields on a customer_profiles row (e.g. from profiler.py)."""
    # Never write sentinel/invalid values to the DB
    fields = {k: v for k, v in fields.items() if not (k == "avatar_type" and v in ("unclear", None, ""))}
    if not fields:
        return {}
    result = (
        supabase.table("customer_profiles")
        .update(fields)
        .eq("session_id", session_id)
        .execute()
    )
    return result.data[0] if result.data else {}


# ---------------------------------------------------------------------------
# conversations + messages
# ---------------------------------------------------------------------------

def get_or_create_conversation(session_id: str, customer_id: Optional[str] = None) -> dict[str, Any]:
    """Fetch the conversations row for this session, creating it if new.
    Requires a customer_profiles row to already exist (FK constraint)."""
    result = (
        supabase.table("conversations")
        .select("*")
        .eq("session_id", session_id)
        .execute()
    )
    if result.data:
        return result.data[0]

    insert_payload = {"session_id": session_id, "current_stage": "greeting"}    
    if customer_id:
        insert_payload["customer_id"] = customer_id

    created = supabase.table("conversations").insert(insert_payload).execute()
    return created.data[0]


def set_stage(session_id: str, stage: str) -> None:
    """Move a session to a new stage. Valid values match the DB check
    constraint: relationship_builder, profiler, problem_solver, stylist,
    sales_consultant."""
    supabase.table("conversations").update({"current_stage": stage}).eq(
        "session_id", session_id
    ).execute()


def add_message(session_id: str, role: str, content: str) -> dict[str, Any]:
    """Append one message to the messages table. role must be one of
    'user', 'assistant', 'system'."""
    result = (
        supabase.table("messages")
        .insert({"session_id": session_id, "role": role, "content": content})
        .execute()
    )
    return result.data[0]


def get_history(session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent `limit` messages for a session, oldest first —
    ready to hand straight to a LangChain message list."""
    result = (
        supabase.table("messages")
        .select("role, content, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(result.data))


# ---------------------------------------------------------------------------
# shortlisted_products
# ---------------------------------------------------------------------------

def add_to_shortlist(session_id: str, product_id: str, customer_id: Optional[str] = None) -> None:
    """Add a product to the shortlist. Relies on the (session_id, product_id)
    unique constraint — re-adding the same product is a safe no-op."""
    payload = {"session_id": session_id, "product_id": product_id}
    if customer_id:
        payload["customer_id"] = customer_id
    supabase.table("shortlisted_products").upsert(
        payload, on_conflict="session_id,product_id"
    ).execute()


def get_shortlist(session_id: str) -> list[dict[str, Any]]:
    result = (
        supabase.table("shortlisted_products")
        .select("*")
        .eq("session_id", session_id)
        .order("added_at", desc=False)
        .execute()
    )
    return result.data


# ---------------------------------------------------------------------------
# convenience: full session bootstrap
# ---------------------------------------------------------------------------

def bootstrap_session(session_id: str, customer_id: Optional[str] = None) -> dict[str, Any]:
    """Called once at the start of every /api/chat turn. Ensures profile +
    conversation rows exist and returns everything the orchestrator needs
    to decide what stage to run next."""
    profile = get_or_create_profile(session_id, customer_id)
    conversation = get_or_create_conversation(session_id, customer_id)
    history = get_history(session_id)
    shortlist = get_shortlist(session_id)
    return {
        "profile": profile,
        "conversation": conversation,
        "history": history,
        "shortlist": shortlist,
    }
