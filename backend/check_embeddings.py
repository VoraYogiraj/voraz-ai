from supabase import create_client
from config import settings

client = create_client(settings.supabase_url, settings.supabase_service_role_key)
result = client.table("products").select("id, title, embedding").execute()
for row in result.data:
    status = "NULL" if row["embedding"] is None else str(len(row["embedding"])) + " dims"
    print(row["title"], "->", status)
