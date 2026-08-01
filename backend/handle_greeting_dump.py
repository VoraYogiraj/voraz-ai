def _handle_greeting(session_id: str, message: str, profile: dict) -> str:
    """First turn — warm welcome, classify intent, move to profiling."""
    from agents.intent_classifier import classify_intent
    from agents.memory_store import update_profile

    try:
        avatar_type = classify_intent(message)
        if avatar_type != "unclear":
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