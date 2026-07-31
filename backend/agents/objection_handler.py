import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

supabase = get_supabase()

PLAYBOOK_PATH = os.path.join(os.path.dirname(__file__), "..", "objection_playbook.json")

_playbook_cache: Optional[list[dict]] = None


def _load_playbook() -> list[dict]:
    """Loads and caches objection_playbook.json. Reload requires a process restart —
    fine for this use case since the file changes rarely and is not hot-reloaded elsewhere."""
    global _playbook_cache
    if _playbook_cache is not None:
        return _playbook_cache

    try:
        with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _playbook_cache = data.get("objections", [])
        logger.info(f"Loaded {len(_playbook_cache)} objection types from playbook")
    except Exception as e:
        logger.error(f"Failed to load objection_playbook.json: {e}", exc_info=True)
        _playbook_cache = []

    return _playbook_cache


def detect_objection(user_message: str) -> Optional[dict]:
    """Case-insensitive substring match of user_message against each objection
    type's trigger_phrases. Returns the first matching objection dict
    (objection_type, resolution_template, linked_action), or None if no match.
    """
    if not user_message:
        return None

    message_lower = user_message.lower()
    playbook = _load_playbook()

    for objection in playbook:
        for phrase in objection.get("trigger_phrases", []):
            if phrase.lower() in message_lower:
                logger.info(f"Objection detected: {objection['objection_type']} (matched: '{phrase}')")
                return objection

    return None


def _log_objection(
    session_id: Optional[str],
    objection_type: str,
    resolution_given: str,
    resolved: Optional[bool] = None,
) -> None:
    """Writes a detection event to objections_log. resolved is None (unknown/pending)
    until linked_action handlers are actually implemented and can confirm outcome."""
    if not session_id:
        logger.warning("No session_id provided — skipping objections_log write")
        return
    try:
        supabase.table("objections_log").insert({
            "session_id": session_id,
            "objection_type": objection_type,
            "resolution_given": resolution_given,
            "resolved": resolved,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"Failed to write objections_log: {e}", exc_info=True)


def handle_objection(user_message: str, session_id: Optional[str] = None) -> Optional[dict]:
    """Main entry point. Detects an objection in user_message and returns a dict
    with resolution_template and objection_type if found, running linked_action
    if present, and logging the detection. Returns None if no objection detected —
    caller should fall through to normal stylist/agent flow in that case.
    """
    objection = detect_objection(user_message)
    if not objection:
        return None

    result = {
        "objection_type": objection["objection_type"],
        "resolution_template": objection["resolution_template"],
    }

    linked_action = objection.get("linked_action")
    if linked_action:
        try:
            action_result = _run_linked_action(linked_action, user_message, session_id)
            result["action_result"] = action_result
        except Exception as e:
            logger.error(f"Linked action '{linked_action}' failed: {e}", exc_info=True)
            result["action_result"] = None

    _log_objection(
        session_id=session_id,
        objection_type=result["objection_type"],
        resolution_given=result["resolution_template"],
        resolved=None,  # unknown until linked_action is real and can confirm outcome
    )

    return result


def _run_linked_action(action_name: str, user_message: str, session_id: Optional[str]) -> Optional[dict]:
    """Dispatches to a linked action by name. Not yet implemented — the two
    actions referenced in the current playbook (check_production_timeline,
    check_size_availability) need real backend hooks (Shopify stock check,
    production calendar) that don't exist yet. Logs and returns None until built."""
    logger.warning(f"Linked action '{action_name}' is not yet implemented — skipping.")
    return None