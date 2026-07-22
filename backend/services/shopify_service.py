import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)

SHOPIFY_BASE = f"https://{settings.shopify_store_domain}/admin/api/2025-01"
GRAPHQL_URL = f"{SHOPIFY_BASE}/graphql.json"
HEADERS = {
    "X-Shopify-Access-Token": settings.shopify_admin_api_key,
    "Content-Type": "application/json"
}

PRODUCTS_QUERY = """
query GetProducts($cursor: String) {
  products(first: 50, after: $cursor, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        title
        handle
        descriptionHtml
        tags
        images(first: 1) { edges { node { url } } }
        variants(first: 1) { edges { node { price } } }
        metafields(first: 20) {
          edges { node { namespace key value } }
        }
      }
    }
  }
}
"""

async def get_all_products():
    all_products = []
    cursor = None

    async with httpx.AsyncClient() as client:
        while True:
            try:
                payload = {"query": PRODUCTS_QUERY, "variables": {"cursor": cursor}}
                response = await client.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    logger.error(f"Shopify GraphQL error: {data['errors']}")
                    break

                products_data = data["data"]["products"]
                for edge in products_data["edges"]:
                    node = edge["node"]
                    metafields = {
                        mf["node"]["key"].lower(): mf["node"]["value"]
                        for mf in node["metafields"]["edges"]
                    }
                    all_products.append({
                        "id": node["id"].split("/")[-1],
                        "title": node["title"],
                        "handle": node["handle"],
                        "body_html": node["descriptionHtml"],
                        "tags": ", ".join(node["tags"]),
                        "images": [{"src": node["images"]["edges"][0]["node"]["url"]}] if node["images"]["edges"] else [],
                        "variants": [{"price": node["variants"]["edges"][0]["node"]["price"]}] if node["variants"]["edges"] else [],
                        "metafields": metafields
                    })

                page_info = products_data["pageInfo"]
                if not page_info["hasNextPage"]:
                    break
                cursor = page_info["endCursor"]

            except Exception as e:
                logger.error(f"Failed to fetch Shopify products: {e}")
                break

    return all_products