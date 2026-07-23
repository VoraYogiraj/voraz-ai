-- supabase/quiz_filter_fn.sql
-- Hard-filter (metafield match) product query for the quiz flow.
-- Parallel to match_products() in vector_search_fn.sql, but no embeddings —
-- pure WHERE-clause filtering. Occasion / order_type / silhouette / vibe are
-- always applied when passed (structural, never loosened). Color and price
-- are the only params the caller (quiz_filter_tool.py) should re-call with
-- as NULL when loosening a zero-result query — color dropped first, then price.

CREATE OR REPLACE FUNCTION match_products_filtered(
  filter_occasion text DEFAULT NULL,
  filter_order_type text DEFAULT NULL,
  filter_silhouette text DEFAULT NULL,
  filter_fit_type text DEFAULT NULL,
  filter_vibe text[] DEFAULT NULL,      -- array overlap match against products.vibe
  filter_color text DEFAULT NULL,       -- single color match against color_palette array (loosenable)
  filter_min_price numeric DEFAULT NULL, -- loosenable
  filter_max_price numeric DEFAULT NULL, -- loosenable
  match_count int DEFAULT 12
)
RETURNS TABLE (
  product_id uuid,
  shopify_product_id text,
  title text,
  description text,
  price_inr numeric,
  starting_price_inr numeric,
  order_type text,
  tags text[],
  occasion text,
  color_palette text[],
  style_keywords text[],
  vibe text[],
  silhouette text,
  fit_type text,
  image_urls text[],
  product_url text,
  total_count bigint
)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
  SELECT
    p.id as product_id,
    p.shopify_product_id,
    p.title,
    p.description,
    p.price_inr,
    p.starting_price_inr,
    p.order_type,
    p.tags,
    p.occasion,
    p.color_palette,
    p.style_keywords,
    p.vibe,
    p.silhouette,
    p.fit_type,
    p.image_urls,
    p.product_url,
    COUNT(*) OVER() as total_count
  FROM products p
  WHERE p.is_available = true
    AND (filter_occasion IS NULL OR p.occasion ILIKE filter_occasion)
    AND (filter_order_type IS NULL OR p.order_type = filter_order_type)
    AND (filter_silhouette IS NULL OR p.silhouette ILIKE filter_silhouette)
    AND (filter_fit_type IS NULL OR p.fit_type ILIKE filter_fit_type)
    AND (filter_vibe IS NULL OR p.vibe && filter_vibe)
    AND (filter_color IS NULL OR EXISTS (
          SELECT 1 FROM unnest(p.color_palette) c WHERE c ILIKE filter_color
        ))
    AND (filter_min_price IS NULL OR COALESCE(p.starting_price_inr, p.price_inr) >= filter_min_price)
    AND (filter_max_price IS NULL OR COALESCE(p.starting_price_inr, p.price_inr) <= filter_max_price)
  ORDER BY p.updated_at DESC
  LIMIT match_count;
$$;