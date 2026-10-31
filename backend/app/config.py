"""App settings, read from environment variables (.env in dev)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # local = free models (Ollama, Cloudflare), prod = official Meta models,
    # mock = canned answers, no network (for tests and offline work)
    mode: str = "local"

    # Official Meta Model API (OpenAI-compatible)
    meta_api_key: str = ""
    meta_base_url: str = "https://api.meta.ai/v1"
    meta_chat_model: str = "muse-spark-1.3"
    meta_image_model: str = "muse-image-1.0"

    # Muse Spark Open on Baseten (backup in prod, open-weight bonus)
    baseten_api_key: str = ""
    baseten_base_url: str = "https://inference.baseten.co/v1"
    baseten_model: str = "meta-models/muse-spark-open"   # check on Baseten once there is a key

    # Cloudflare Workers AI (free tier, local backup)
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_chat_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    cloudflare_vision_model: str = "@cf/meta/llama-4-scout-17b-16e-instruct"
    cloudflare_image_model: str = "@cf/black-forest-labs/flux-1-schnell"

    # Groq (free tier, fast; local voter only. It retired Llama 4, so its image model is Qwen)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "qwen/qwen3.8-27b"   # Groq retired Llama 4 in July 2026

    # Google Gemini (free tier, local voter only; production stays on Meta models)
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-3.8-flash"

    # Ollama on your laptop (free, offline)
    ollama_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_vision_model: str = "qwen2.5vl:7b"

    # all of them answer when naming rooms (they vote); the first one is preferred for single answers
    local_vision_chain: str = "cloudflare,ollama,gemini,groq"

    # Cache every AI call so repeat runs are free. AI_CACHE=false always asks the models again.
    ai_cache: bool = True
    cache_dir: Path = ROOT / ".cache" / "ai"
    request_timeout: float = 120.0

    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()