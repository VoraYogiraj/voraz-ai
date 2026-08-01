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
