-- 1. Enable Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Products Table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shopify_product_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price_inr NUMERIC(10,2),
    compare_at_price_inr NUMERIC(10,2),
    tags TEXT[],
    occasion TEXT,
    color_palette TEXT[],
    style_keywords TEXT[],
    image_urls TEXT[],
    product_url TEXT,
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Product Embeddings Table (pgvector)
CREATE TABLE IF NOT EXISTS product_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL, -- Dimension for OpenAI text-embedding-3-small
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Chat Sessions Table
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_token TEXT UNIQUE NOT NULL,
    messages JSONB DEFAULT '[]'::jsonb,
    style_preferences JSONB DEFAULT '{}'::jsonb,
    whatsapp_number TEXT,
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Customer Profiles Table
CREATE TABLE IF NOT EXISTS customer_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shopify_customer_id TEXT,
    whatsapp_number TEXT UNIQUE,
    email TEXT,
    name TEXT,
    style_preferences JSONB DEFAULT '{}'::jsonb,
    last_seen_products TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Indexes for Performance
CREATE INDEX ON product_embeddings(product_id);
CREATE INDEX ON chat_sessions(session_token);
CREATE INDEX ON customer_profiles(whatsapp_number);
-- IVFFlat index for vector search
CREATE INDEX ON product_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 7. Security (Row Level Security)
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_profiles ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access
CREATE POLICY "Service role full access" ON products FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access" ON product_embeddings FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access" ON chat_sessions FOR ALL TO service_role USING (true);
CREATE POLICY "Service role full access" ON customer_profiles FOR ALL TO service_role USING (true);

-- =====================================================================
-- 8. QUIZ FEATURE — Additive schema changes (safe to re-run)
-- =====================================================================

-- 8a. Products: hard-filter columns
ALTER TABLE products ADD COLUMN IF NOT EXISTS order_type TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS vibe TEXT[];
ALTER TABLE products ADD COLUMN IF NOT EXISTS silhouette TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS fit_type TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS starting_price_inr NUMERIC(10,2); -- NULL = price on request (Bespoke)

-- Constrain order_type to the three known codes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'products_order_type_check'
    ) THEN
        ALTER TABLE products ADD CONSTRAINT products_order_type_check
            CHECK (order_type IS NULL OR order_type IN ('ready_to_ship', 'choose_customize', 'fully_bespoke'));
    END IF;
END $$;

-- 8b. Chat Sessions: quiz state (resumable per session)
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS quiz_answers JSONB DEFAULT '{}'::jsonb;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS quiz_step TEXT; -- current question id, for resume
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS quiz_completed BOOLEAN DEFAULT false;

-- 8c. Customer Profiles: lead capture fields
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS inspiration_image_url TEXT;
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS inspiration_link TEXT;
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS lead_source TEXT; -- 'quiz_ready_to_ship' | 'quiz_customize' | 'quiz_bespoke' | 'chat'
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS lead_captured_at TIMESTAMPTZ;

-- 8d. Indexes for the new hard-filter columns (quiz path is filter-heavy, not vector-heavy)
CREATE INDEX IF NOT EXISTS idx_products_order_type ON products(order_type);
CREATE INDEX IF NOT EXISTS idx_products_silhouette ON products(silhouette);
CREATE INDEX IF NOT EXISTS idx_products_fit_type ON products(fit_type);
CREATE INDEX IF NOT EXISTS idx_products_vibe ON products USING GIN(vibe);
CREATE INDEX IF NOT EXISTS idx_products_occasion ON products(occasion);