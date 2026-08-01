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
