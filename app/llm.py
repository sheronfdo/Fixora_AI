"""LLM access via OpenRouter (OpenAI-compatible gateway).

OpenRouter exposes a single OpenAI-style endpoint that routes to many models
(Claude, GPT, Gemini, Llama, …). We reach it through LangChain's ChatOpenAI
by pointing `base_url` at OpenRouter and passing the OpenRouter key. Switching
models is a config change (`OPENROUTER_MODEL`), never a code change.

Imports are lazy so the rest of the service (health, auth) runs without the
heavy LLM dependencies installed — they come online in Phase 5.
"""
from functools import lru_cache

from .config import get_settings
from .errors import upstream_unavailable


@lru_cache
def get_chat_model(temperature: float = 0.0):
    """Return a configured chat model, or raise 503 if not configured."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise upstream_unavailable("LLM (OpenRouter) is not configured")

    from langchain_openai import ChatOpenAI  # lazy

    return ChatOpenAI(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        default_headers={
            # OpenRouter attribution headers (optional but recommended).
            "HTTP-Referer": settings.openrouter_site_url,
            "X-Title": settings.openrouter_app_name,
        },
    )


def llm_configured() -> bool:
    return bool(get_settings().openrouter_api_key)
