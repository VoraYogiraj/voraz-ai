from supabase import create_client
from config import settings

client = create_client(settings.supabase_url, settings.supabase_service_role_key)
result = client.rpc("exec_sql", {"sql": "SELECT prosrc FROM pg_proc WHERE proname = %s" }).execute()
print(result.data)
