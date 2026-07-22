-- Function to perform semantic search with filters
CREATE OR REPLACE FUNCTION match_products(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 5,
  filter_occasion text DEFAULT NULL,
  filter_min_price numeric DEFAULT NULL,
  filter_max_price numeric DEFAULT NULL
)
RETURNS TABLE (
  product_id uuid,
  shopify_product_id text,
  title text,
  description text,
  price_inr numeric,
  tags text[],
  occasion text,
  color_palette text[],
  image_urls text[],
  product_url text,
  similarity float
)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
  SELECT
    p.id as product_id,
    p.shopify_product_id,
    p.title,
    p.description,
    p.price_inr,
    p.tags,
    p.occasion,
    p.color_palette,
    p.image_urls,
    p.product_url,
    1 - (pe.embedding <=> query_embedding) AS similarity
  FROM product_embeddings pe
  JOIN products p ON pe.product_id = p.id
  WHERE p.is_available = true
    AND (filter_occasion IS NULL OR p.occasion ILIKE filter_occasion)
    AND (filter_min_price IS NULL OR p.price_inr >= filter_min_price)
    AND (filter_max_price IS NULL OR p.price_inr <= filter_max_price)
    AND (1 - (pe.embedding <=> query_embedding)) > match_threshold
  ORDER BY pe.embedding <=> query_embedding ASC
  LIMIT match_count;
$$;

-- Simpler function for category browsing
CREATE OR REPLACE FUNCTION search_products_by_occasion(
  filter_occasion text
)
RETURNS TABLE (
  product_id uuid,
  shopify_product_id text,
  title text,
  description text,
  price_inr numeric,
  tags text[],
  occasion text,
  color_palette text[],
  image_urls text[],
  product_url text
)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
  SELECT id, shopify_product_id, title, description, price_inr, tags, occasion, color_palette, image_urls, product_url
  FROM products
  WHERE is_available = true AND occasion ILIKE filter_occasion
  ORDER BY price_inr ASC;
$$;