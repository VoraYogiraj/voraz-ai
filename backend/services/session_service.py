import uuid
import logging
from datetime import datetime, timedelta
from services.supabase_client import supabase
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)

def create_session() -> dict:
    """Create new chat session. Returns session dict or None on failure."""
    session_token = str(uuid.uuid4())
    data = {
        "session_token": session_token,
        "messages": [],
        "style_preferences": {},
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        result = supabase.table("chat_sessions").insert(data).execute()
        if result.data:
            return result.data[0]
        logger.error("Insert returned empty data")
        return None
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        return None

def get_session(session_token: str) -> dict:
    """Fetch session by token. Returns dict or None."""
    try:
        result = supabase.table("chat_sessions").select("*").eq("session_token", session_token).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        return None

def append_message(session_token: str, role: str, content: str) -> bool:
    """Append message to session. Returns True on success."""
    if not session_token:
        return False
    
    new_message = {
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    try:
        # Atomic append: fetch, mutate, push back
        session = get_session(session_token)
        if not session:
            return False
        
        messages = session.get("messages", [])
        messages.append(new_message)
        
        supabase.table("chat_sessions").update({"messages": messages}).eq("session_token", session_token).execute()
        return True
    except Exception as e:
        logger.error(f"Error appending message to {session_token}: {e}")
        return False

def get_session_history_for_langchain(session_token: str) -> list:
    """Fetch session history as LangChain BaseMessage objects."""
    session = get_session(session_token)
    if not session:
        return []
    
    formatted = []
    for msg in session.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            formatted.append(HumanMessage(content=content))
        elif role == "assistant":
            formatted.append(AIMessage(content=content))
    
    return formatted

def cleanup_old_sessions(days: int = 7) -> int:
    """Delete sessions older than N days. Returns count deleted."""
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        result = supabase.table("chat_sessions").delete().lt("created_at", cutoff).execute()
        logger.info(f"Cleaned up old sessions (older than {days}d)")
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {e}")
        return 0