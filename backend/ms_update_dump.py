def update_profile(session_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Patch specific fields on a customer_profiles row (e.g. from profiler.py)."""
    result = (
        supabase.table("customer_profiles")
        .update(fields)
        .eq("session_id", session_id)
        .execute()
    )
    return result.data[0] if result.data else {}
