from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional


class Settings(BaseSettings):
    # Database
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "neurolearn"
    MYSQL_PASSWORD: str = "neurolearn_pass"
    MYSQL_DATABASE: str = "neurolearn"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # AI Keys (legacy — kept for backward compatibility)
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    SERPER_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # Certificate Signing
    ED25519_KEY_PATH: str = ""
    CERTIFICATE_ISSUER_DID: str = "did:web:neurolearn.edu"

    # App
    APP_SECRET_KEY: str = "change-this-secret-key"
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost,http://localhost:3000,http://localhost:8080"
    LOG_LEVEL: str = "INFO"

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Rate Limiting
    RATE_LIMIT_GENERAL: str = "60/minute"
    RATE_LIMIT_AI: str = "10/minute"

    # Ollama Cloud
    OLLAMA_BASE_URL: str = "https://ollama.com"
    OLLAMA_API_KEY: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors(cls, v):
        if not v:
            return "http://localhost,http://localhost:3000,http://localhost:8080"
        return v

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def SQLITE_URL(self) -> str:
        return "sqlite+aiosqlite:///./neurolearn.db"

    @property
    def cors_origins_list(self) -> list:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        case_sensitive = True
        extra = "allow"


_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

settings = get_settings()
