import asyncio
import httpx
from langchain_core.tools import tool
from config import settings

async def _send_whatsapp(to: str, text: str):
    # Guard: bail if WhatsApp not configured
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return False
    
    url = f"{settings.whatsapp_api_url}/{settings.whatsapp_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=payload, headers=headers, timeout=10.0)
            return r.status_code == 200
        except httpx.RequestError:
            return False

@tool
def send_style_summary_whatsapp(phone_number: str, customer_name: str, product_summary: str) -> str:
    """Send a personalized style summary to the customer on WhatsApp."""
    # Skip if not configured
    if not settings.whatsapp_access_token:
        return "WhatsApp not configured. Style summary ready to share manually."
    
    msg = f"Hi {customer_name}! 🌸 Here are your VORA picks:\n\n{product_summary}\n\nOur team is here if you need styling help! — Team VORA"
    success = asyncio.run(_send_whatsapp(phone_number, msg))
    return "Sent successfully!" if success else "Failed to send."