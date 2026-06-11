from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres.uyukrupvxcrvihwntzjp:Decisionminds%402026@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
    SECRET_KEY: str = "slm-super-secret-key-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL: str = "llama-3.3-70b-versatile"

    class Config:
        env_file = ".env"
        extra   = "ignore"   # allow DB_HOST/GROQ_API_KEY/etc. in .env without failing

settings = Settings()
