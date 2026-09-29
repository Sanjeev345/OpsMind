"""Application settings loaded from environment / .env (repo root or backend/)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"          # diagnosis + lesson distillation
    groq_agent_model: str = "openai/gpt-oss-20b"     # tool-calling loop (separate Groq TPM bucket)
    groq_agent_fallback_models: str = "qwen/qwen3.8-27b,openai/gpt-oss-120b"  # failover on rate limit
    groq_structured_fallback_models: str = "qwen/qwen3.8-27b,openai/gpt-oss-20b"  # diagnosis failover
    groq_timeout_seconds: float = 60.0

    hindsight_api_key: str = ""
    hindsight_base_url: str = "https://api.hindsight.vectorize.io"
    hindsight_bank_id: str = "opsmind"
    hindsight_timeout_seconds: float = 60.0

    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    max_tool_iterations: int = 5
    max_llm_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
