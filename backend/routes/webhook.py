from fastapi import APIRouter, Request, Header
from fastapi.responses import PlainTextResponse
from config import settings
from agents.orchestrator import run_turn
from tools.whatsapp_tool import send_style_summary_whatsapp
import logging
import hashlib
import hmac

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_whatsapp_hmac(body: str, signature: str) -> bool:
    """Verify WhatsApp webhook signature."""
    if not settings.whatsapp_webhook_secret:
        logger.warning("WHATSAPP_WEBHOOK_SECRET not configured, skipping HMAC check")
        return True
    
    computed = hmac.new(
        settings.whatsapp_webhook_secret.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)

def verify_shopify_hmac(body: bytes, signature: str) -> bool:
    """Verify Shopify webhook signature."""
    if not settings.shopify_webhook_secret:
        logger.warning("SHOPIFY_WEBHOOK_SECRET not configured, skipping HMAC check")
        return True
    
    computed = hmac.new(
        settings.shopify_webhook_secret.encode(),
        body,
        hashlib.sha256
    ).digest()
    computed_b64 = hashlib.sha256(computed).hexdigest()  # Shopify sends base64
    return hmac.compare_digest(computed_b64, signature.replace("sha256=", ""))

@router.get("/whatsapp")
async def verify_whatsapp(request: Request):
    """Handshake for Meta WhatsApp Webhook setup"""
    params = request.query_params
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    
    if token == settings.whatsapp_verify_token and challenge:
        return PlainTextResponse(challenge)
    
    logger.warning("WhatsApp verification failed")
    return {"error": "Verification failed"}

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    """Handles incoming WhatsApp messages"""
    body = await request.body()

    if x_hub_signature_256 and not verify_whatsapp_hmac(body.decode(), x_hub_signature_256):
        logger.error("WhatsApp signature verification failed")
        return {"status": "error", "message": "Invalid signature"}

    try:
        data = await request.json()

        entry = data.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
        if 'messages' not in entry:
            return {"status": "ok"}

        message = entry['messages'][0]
        phone = message.get('from')
        text = message.get('text', {}).get('body', '').strip()

        if not phone or not text:
            return {"status": "ok"}

        # Deterministic session id from phone number — keeps the same
        # conversation/customer_profiles/messages rows across turns
        # without needing client-side token storage.
        session_id = f"whatsapp-{phone}"

        result = run_turn(session_id, text, phone)
        reply = result["reply"]

        try:
            send_style_summary_whatsapp.invoke({
                "phone_number": phone,
                "customer_name": "Customer",
                "product_summary": reply,
            })
        except Exception as e:
            logger.error(f"Failed to send WhatsApp reply: {e}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"WhatsApp Webhook Error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/shopify/abandoned-cart")
async def shopify_abandoned_cart(
    request: Request,
    x_shopify_hmac_sha256: str = Header(None)
):
    """Logs abandoned carts from Shopify"""
    body = await request.body()
    
    # Verify signature
    if x_shopify_hmac_sha256 and not verify_shopify_hmac(body, x_shopify_hmac_sha256):
        logger.error("Shopify signature verification failed")
        return {"status": "error", "message": "Invalid signature"}
    
    try:
        data = await request.json()
        checkout_id = data.get('id', 'unknown')
        logger.info(f"Abandoned cart received: {checkout_id}")
        # n8n will handle the actual logic, this is just for validation
        return {"status": "received"}
    
    except Exception as e:
        logger.error(f"Shopify webhook error: {e}", exc_info=True)
        return {"status": "error"}