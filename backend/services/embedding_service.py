import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

model = SentenceTransformer("all-MiniLM-L6-v2")

def generate_embedding(text: str) -> list[float]:
    try:
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as e:
        logger.error(f"Embedding generation error: {e}")
        return []

def build_product_embedding_text(product: dict) -> str:
    return f"{product.get('title')}. {product.get('description')}. Occasion: {product.get('occasion')}."