import os
import re
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Project Info
    PROJECT_NAME: str = "Legal AI Backend"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PORT: int = 8000

    # Security / Auth
    JWT_SECRET_KEY: str = "insecure-default-change-me-in-production-1234567890"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # PostgreSQL Database URL
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/legal_ai_db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, v: str) -> str:
        if not v:
            return "postgresql+asyncpg://postgres:postgres@localhost:5432/legal_ai_db"
        
        v = v.strip()
        # Convert standard URL schemes to asyncpg
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Normalize parameters for asyncpg compatibility:
        # asyncpg does not support channel_binding or sslmode parameters
        v = re.sub(r'[?&]channel_binding=[^&]+', '', v)
        v = v.replace("sslmode=", "ssl=")
        return v

    # Weaviate Vector Database
    WEAVIATE_URL: str = ""
    WEAVIATE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    @field_validator("WEAVIATE_URL", mode="before")
    @classmethod
    def assemble_weaviate_url(cls, v: str) -> str:
        if not v:
            return ""
        v = v.strip()
        if v and not v.startswith("http://") and not v.startswith("https://"):
            v = f"https://{v}"
        return v

    # Collection Name for Vector Storage (matches user's Weaviate instance collection)
    DEFAULT_VECTOR_COLLECTION: str = "LegalChunk"

    # Groq LLM Configuration
    GROQ_API_KEY: str = ""
    GROQ_DEFAULT_MODEL: str = "qwen/qwen3.8-27b"



settings = Settings()
