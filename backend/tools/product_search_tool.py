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
    max_results: int = 5
) -> str:
    """Search for VORA bridal wear products based on style description, occasion, and budget.
    Use this when the customer describes what they're looking for.
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
            "filter_max_price": max_price
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