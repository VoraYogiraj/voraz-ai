import logging
from typing import Optional
from langchain_core.tools import tool
from services.embedding_service import generate_embedding
from services.supabase_client import supabase

logger = logging.getLogger(__name__)

# Maps casual customer language -> vocabulary that matches your catalog's
# actual occasion tags, so it strengthens the embedding match instead of
# just appending words the model has to guess the relevance of.
OCCASION_QUERY_TERMS = {
    "wedding": "bridal",
    "weddings": "bridal",
    "shaadi": "bridal",
    "marriage": "bridal",
    "bride": "bridal",
    "sangeet": "sangeet",
    "mehndi": "sangeet",
    "engagement": "engagement",
    "roka": "engagement",
    "reception": "reception",
}


def expand_occasion(occasion: Optional[str]) -> Optional[str]:
    if not occasion:
        return occasion
    cleaned = occasion.strip().lower()
    return OCCASION_QUERY_TERMS.get(cleaned, occasion)


@tool
def search_products(
    query: str,
    occasion: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    order_type: Optional[str] = None,
    max_results: int = 5
) -> str:
    """Search for VORA bridal wear products based on style description, occasion, and budget.
    Use this when the customer describes what they're looking for.

    order_type MUST be passed exactly as given in the system prompt's customer
    context (e.g. "Ready to Ship", "Choose & Customize", "Fully Bespoke") — do
    not translate, guess, or omit it if it was provided.
    """
    try:
        # Fold occasion into the embedding query text (normalized to catalog
        # vocabulary) rather than filtering on it in the DB — the catalog's
        # occasion tags don't reliably match customer phrasing like "wedding".
        expanded_occasion = expand_occasion(occasion)
        full_query = f"{query} {expanded_occasion}".strip() if expanded_occasion else query

        logger.info(f"Searching products: query={full_query}")
        vector = generate_embedding(full_query)
        logger.info(f"Generated embedding: {len(vector)} dimensions")

        rpc_params = {
            "query_embedding": vector,
            "match_threshold": 0.3,
            "match_count": max_results,
            "filter_occasion": None,
            "filter_min_price": min_price,
            "filter_max_price": max_price,
            "filter_order_type": order_type
        }

        response = supabase.rpc("match_products", rpc_params).execute()
        results = response.data
        logger.info(f"RPC returned {len(results)} results")

        if not results:
            return "No products found. The collection may be limited — suggest the customer contact VORAZ directly."

        formatted_results = []
        for p in results:
            colors = p.get('color_palette') or []
            item = (
                f"PRODUCT: {p.get('title', 'Unknown')}\n"
                f"Price: ₹{p.get('price_inr', 0):,.0f}\n"
                f"Occasion: {p.get('occasion', 'N/A')}\n"
                f"Colors: {', '.join(colors)}\n"
                f"Link: {p.get('product_url', '')}\n"
            )
            formatted_results.append(item)

        return "\n---\n".join(formatted_results)
    except Exception as e:
        logger.error(f"Product search error: {e}", exc_info=True)
        return f"Error searching products: {str(e)}"


@tool
def search_products_filtered(
    occasion: Optional[str] = None,
    order_type: Optional[str] = None,
    silhouette: Optional[str] = None,
    fit_type: Optional[str] = None,
    vibe: Optional[list[str]] = None,
    color: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    max_results: int = 5
) -> str:
    """Search VORA products using structured filters (occasion, order type,
    silhouette, fit, vibe, color, price range) already known from the
    customer's profile. Prefer this over search_products when these slots
    are already known — it filters directly rather than relying on semantic
    similarity. Falls back to no results if filters are too narrow; in that
    case try search_products instead.
    """
    try:
        expanded_occasion = expand_occasion(occasion)

        rpc_params = {
            "filter_occasion": expanded_occasion,
            "filter_order_type": order_type,
            "filter_silhouette": silhouette,
            "filter_fit_type": fit_type,
            "filter_vibe": vibe,
            "filter_color": color,
            "filter_min_price": min_price,
            "filter_max_price": max_price,
            "match_count": max_results
        }

        logger.info(f"Filtered search: {rpc_params}")
        response = supabase.rpc("match_products_filtered", rpc_params).execute()
        results = response.data
        logger.info(f"RPC returned {len(results)} results")

        if not results:
            return "No products found matching these filters. Try search_products for a broader semantic search instead."

        formatted_results = []
        for p in results:
            colors = p.get('color_palette') or []
            occasions = p.get('occasion') or []
            item = (
                f"PRODUCT: {p.get('title', 'Unknown')}\n"
                f"Price: ₹{p.get('price_inr', 0):,.0f}\n"
                f"Occasion: {', '.join(occasions) if isinstance(occasions, list) else occasions}\n"
                f"Silhouette: {p.get('silhouette', 'N/A')}\n"
                f"Fit: {p.get('fit', 'N/A')}\n"
                f"Colors: {', '.join(colors)}\n"
                f"Link: {p.get('product_url', '')}\n"
            )
            formatted_results.append(item)

        return "\n---\n".join(formatted_results)
    except Exception as e:
        logger.error(f"Filtered product search error: {e}", exc_info=True)
        return f"Error searching products: {str(e)}"