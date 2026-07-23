import logging
from openai import OpenAI
from config import settings

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
)

def generate_embedding(text: str) -> list[float]:
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding generation error: {e}")
        return []

def build_product_embedding_text(product: dict) -> str:
    return f"{product.get('title')}. {product.get('description')}. Occasion: {product.get('occasion')}."