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