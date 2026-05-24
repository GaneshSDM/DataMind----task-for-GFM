"""
Application configuration — loaded from backend/.env via load_dotenv in main.py.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 6543
    db_name: str = "postgres"
    db_user: str = ""
    db_password: str = ""
    db_sslmode: str = "require"

    # LLM — provider-agnostic (OpenAI-compatible)
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_base_url: str = "https://api.groq.com/openai/v1"

    # RAG quality gate
    rag_min_similarity: float = 0.55

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8005

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
