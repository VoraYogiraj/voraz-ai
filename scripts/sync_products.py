import sys
import os
import asyncio
import logging
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from dotenv import load_dotenv
load_dotenv()

from services.shopify_service import get_all_products
from services.embedding_service import generate_embedding, build_product_embedding_text
from services.supabase_client import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_html(raw_html):
    """Removes Shopify HTML tags from descriptions."""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

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
                "occasion": mf.get("occasions", "General"),
                "color_palette": [c.strip() for c in mf.get("color", "").split(",") if c.strip()],
                "embroidery": mf.get("embroidery", ""),
                "fabric": mf.get("fabrics", ""),
                "silhouette": mf.get("silhouette", ""),
                "neckline": mf.get("neckline", ""),
                "sleeve_style": mf.get("sleeve style", ""),
                "fit": mf.get("fit", ""),
                "vibes": mf.get("vibes", ""),
                "short_description": mf.get("short description", ""),
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