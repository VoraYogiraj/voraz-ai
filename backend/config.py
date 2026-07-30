import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # Backend
    port: int = 8000
    environment: str = "development"

    # OpenAI (optional)
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o"

    # OpenRouter
    openrouter_api_key: str
    openrouter_model_id: str = "tencent/hy3:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Shopify
    shopify_store_domain: str
    shopify_access_token: str = ""        
    shopify_admin_api_key: str = ""
    shopify_admin_api_secret: str = ""
    shopify_storefront_api_token: str = ""
    shopify_webhook_secret: str = ""

    ngrok_redirect_uri: str = ""

    # WhatsApp
    whatsapp_api_url: str = "https://graph.facebook.com/v19.0"
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = ""

    # Origins for CORS
    allowed_origins: str = "http://localhost:3000,https://vora.myshopify.com"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()