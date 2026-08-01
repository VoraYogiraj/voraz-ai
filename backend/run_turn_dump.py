def run_turn(
    session_id: str,
    message: str,
    customer_id: Optional[str] = None,
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
    # 1. Bootstrap session (idempotent — safe to call every turn)
    bootstrap_session(session_id, customer_id)

    # 2. Persist user message
    add_message(session_id, "user", message)

    # 3. Get current profile + stage
    profile = get_or_create_profile(session_id, customer_id)
    stage = _current_stage(session_id)
    logger.info(f"[orchestrator] session={session_id} stage={stage}")

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
