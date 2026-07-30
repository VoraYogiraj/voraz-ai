# backend/tools/quiz_filter_tool.py
import logging
from typing import Optional, List, Dict, Any
from services.supabase_client import supabase

logger = logging.getLogger(__name__)

# Order matters: color is dropped before budget when a filter combo returns zero results.
LOOSENING_ORDER = ["color", "price"]


def _run_filter_query(
    occasion: Optional[str],
    order_type: Optional[str],
    silhouette: Optional[str],
    fit_type: Optional[str],
    vibe: Optional[List[str]],
    color: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    match_count: int,
) -> List[Dict[str, Any]]:
    rpc_params = {
        "filter_occasion": occasion,
        "filter_order_type": order_type,
        "filter_silhouette": silhouette,
        "filter_fit_type": fit_type,
        "filter_vibe": vibe,
        "filter_color": color,
        "filter_min_price": min_price,
        "filter_max_price": max_price,
        "match_count": match_count,
    }
    response = supabase.rpc("match_products_filtered", rpc_params).execute()
    return response.data or []


def build_match_reason(product: Dict[str, Any], occasion: Optional[str], vibe: Optional[List[str]]) -> str:
    """One-line reason shown under each result card, e.g. 'Matches your Sangeet + Dramatic pick'."""
    parts = []
    if occasion:
        parts.append(occasion.title())
    product_vibe = product.get("vibes") or []
    matched_vibe = [v for v in product_vibe if vibe and v in vibe]
    if matched_vibe:
        parts.append(matched_vibe[0].title())
    if not parts:
        return "Matches your quiz picks"
    return f"Matches your {' + '.join(parts)} pick"


def filter_products(
    occasion: Optional[str] = None,
    order_type: Optional[str] = None,
    silhouette: Optional[str] = None,
    fit_type: Optional[str] = None,
    vibe: Optional[List[str]] = None,
    color: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    match_count: int = 12,
) -> Dict[str, Any]:
    try:
        loosened: List[str] = []
        current_color = color
        current_min = min_price
        current_max = max_price

        results = _run_filter_query(
            occasion, order_type, silhouette, fit_type, vibe,
            current_color, current_min, current_max, match_count,
        )

        for step in LOOSENING_ORDER:
            if results:
                break
            if step == "color" and current_color is not None:
                current_color = None
                loosened.append("color")
            elif step == "price" and (current_min is not None or current_max is not None):
                current_min = None
                current_max = None
                loosened.append("budget")
            else:
                continue
            results = _run_filter_query(
                occasion, order_type, silhouette, fit_type, vibe,
                current_color, current_min, current_max, match_count,
            )

        for p in results:
            p["match_reason"] = build_match_reason(p, occasion, vibe)

        return {
            "products": results,
            "count": len(results),
            "loosened": loosened,
        }
    except Exception as e:
        logger.error(f"Quiz filter error: {e}", exc_info=True)
        return {"products": [], "count": 0, "loosened": [], "error": str(e)}