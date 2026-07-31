import logging
from supabase import create_client, Client
from config import settings

logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

def get_supabase() -> Client:
    return supabase

async def test_connection():
    try:
        # Try to fetch 1 row from products
        response = supabase.table("products").select("id").limit(1).execute()
        return True
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
        return False
