import sys
import os
import asyncio
import logging
import re
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from dotenv import load_dotenv
load_dotenv()

from services.shopify_service import get_all_products
from services.embedding_service import generate_embedding, build_product_embedding_text
from services.supabase_client import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Metafields that are Shopify "list.single_line_text_field" — value comes back
# as a JSON array string, e.g. '["Silk","Net"]'. Everything else is a plain
# single-line string.
LIST_METAFIELDS = {"occasions", "color", "vibes", "embroidery", "fabrics"}


def clean_html(raw_html):
    """Removes Shopify HTML tags from descriptions."""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html or '')


def parse_metafield_value(mf: dict, key: str):
    """Returns a list for list-type metafields, a plain string otherwise."""
    raw = mf.get(key, "")
    if key in LIST_METAFIELDS:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        # fallback: comma-split in case it wasn't valid JSON for some reason
        return [v.strip() for v in raw.split(",") if v.strip()]
    return raw


async def sync_products():
    logger.info("🚀 Starting VORA Product Sync...")

    products = await get_all_products()
    if not products:
        logger.error("❌ No products found in Shopify. Check your API keys.")
        return

    logger.info(f"📦 Found {len(products)} products. Processing...")

    for p in products:
        try:
            shopify_id = str(p['id'])
            title = p['title']
            description = clean_html(p.get('body_html', ''))
            price = float(p['variants'][0]['price']) if p.get('variants') else 0
            tags = [t.strip() for t in p.get('tags', '').split(',') if t.strip()]

            mf = p.get('metafields', {})
            image_url = p['images'][0]['src'] if p.get('images') else ""
            product_url = f"https://{os.getenv('SHOPIFY_STORE_DOMAIN')}/products/{p['handle']}"

            product_data = {
                "shopify_product_id": shopify_id,
                "title": title,
                "description": description,
                "price_inr": price,
                "tags": tags,

                # list-type metafields -> text[]
                "occasion": parse_metafield_value(mf, "occasions"),
                "color_palette": parse_metafield_value(mf, "color"),
                "vibes": parse_metafield_value(mf, "vibes"),
                "embroidery": parse_metafield_value(mf, "embroidery"),
                "fabric": parse_metafield_value(mf, "fabrics"),

                # single-value metafields -> text
                "silhouette": parse_metafield_value(mf, "silhouettes"),
                "neckline": parse_metafield_value(mf, "neckline"),
                "sleeve_style": parse_metafield_value(mf, "sleeve_style"),
                "fit": parse_metafield_value(mf, "fit_type"),
                "order_type": parse_metafield_value(mf, "order_type"),
                "dupatta": parse_metafield_value(mf, "dupatta"),

                # free-text fields
                "short_description": parse_metafield_value(mf, "short_description"),
                "care_instructions": parse_metafield_value(mf, "care_instructions"),
                "search_keywords": parse_metafield_value(mf, "search_keywords"),
                "who_is_it_for": parse_metafield_value(mf, "who_is_it_for"),
                "product_highlights": parse_metafield_value(mf, "product_highlights"),

                "image_urls": [image_url],
                "product_url": product_url
            }

            res = supabase.table("products").upsert(product_data, on_conflict="shopify_product_id").execute()
            db_product_id = res.data[0]['id']

            embedding_text = build_product_embedding_text(product_data)
            vector = generate_embedding(embedding_text)

            if vector:
                supabase.table("product_embeddings").delete().eq("product_id", db_product_id).execute()
                supabase.table("product_embeddings").insert({
                    "product_id": db_product_id,
                    "embedding": vector
                }).execute()

            logger.info(f"✅ Synced: {title}")
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"⚠️ Error syncing product {p.get('title')}: {e}")

    logger.info("✨ Sync Complete!")

if __name__ == "__main__":
    asyncio.run(sync_products())