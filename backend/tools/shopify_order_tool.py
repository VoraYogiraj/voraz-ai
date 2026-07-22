import asyncio
from langchain_core.tools import tool
from services.shopify_service import get_order, get_orders_by_email

@tool
def get_order_status(order_id: str) -> str:
    """Get real-time order status and tracking information by Shopify order ID."""
    try:
        # Clean order ID (remove # if present)
        clean_id = order_id.replace("#", "").strip()
        order = asyncio.run(get_order(clean_id))
        
        if not order:
            return "I couldn't find an order with that ID. Please check the number in your confirmation email."
        
        items = ", ".join([f"{i['name']} (x{i['quantity']})" for i in order['line_items']])
        status = order.get('fulfillment_status') or 'Unfulfilled'
        
        return (
            f"Order #{order['name']} Status: {status.capitalize()}\n"
            f"Payment: {order['financial_status'].capitalize()}\n"
            f"Items: {items}"
        )
    except Exception as e:
        return f"Error fetching order: {str(e)}"

@tool
def get_orders_by_customer_email(email: str) -> str:
    """Get recent orders for a customer by their email address."""
    try:
        orders = asyncio.run(get_orders_by_email(email))
        if not orders:
            return "No orders found for that email address."
        
        summary = []
        for o in orders[:3]:
            summary.append(f"Order {o['name']}: {o['financial_status']} | Status: {o.get('fulfillment_status', 'Processing')}")
        
        return "\n".join(summary)
    except Exception as e:
        return f"Error: {str(e)}"