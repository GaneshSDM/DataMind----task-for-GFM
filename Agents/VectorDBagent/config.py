"""
RAVEN configuration — loaded from backend/.env via load_dotenv in raven.py.
All keys use extra="ignore" so unrelated backend .env keys don't crash startup.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database (from backend/.env — same keys as other agents)
    db_host:     str = "localhost"
    db_port:     int = 6543
    db_name:     str = "postgres"
    db_user:     str = ""
    db_password: str = ""
    db_sslmode:  str = "require"

    # Embedding model — local or remote API
    embedding_model:    str = "BAAI/bge-large-en-v1.5"
    embedding_dim:      int = 1024
    embedder_base_url:  str = ""   # if set, call remote /v1/embeddings instead of local model
    embedder_api_key:   str = ""   # Bearer token for remote embedder (falls back to LLM_API_KEY)

    # RAG retrieval config
    raven_top_k:        int   = 5
    rag_min_similarity: float = 0.55

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
