import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database URL defaults to local Postgres, with sqlite fallback support
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite+aiosqlite:///./linkplease.db"
    )
    PSEUDOGRAM_API_KEY: str = os.getenv("PSEUDOGRAM_API_KEY", "mock_key_test_123")
    PSEUDOGRAM_BASE_URL: str = os.getenv("PSEUDOGRAM_BASE_URL", "https://pseudogram-api.onrender.com")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
    
    # Rate limit settings for PseudoGram Mock API: 10 calls / 60 seconds
    RATE_LIMIT_MAX_REQUESTS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: float = 60.0
    
    # Worker polling configuration
    WORKER_POLL_INTERVAL: float = 0.5
    RECONCILIATION_INTERVAL: float = 2.0
    MAX_RETRY_ATTEMPTS: int = 5
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
