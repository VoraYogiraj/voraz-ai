def _profile_ready(profile: dict) -> bool:
    """True if enough slots are filled to move to styling."""
    filled = sum(
        1 for slot in PROFILE_SLOTS_REQUIRED
        if profile.get(slot) not in (None, "", [], {})
    )
    return filled >= 2  # at least 2 of 3 required slots
