"""Fixora AI Service — FastAPI application factory.

Phase 4 delivers the secure foundation: health check, Supabase JWT
verification, the vehicle ownership guard, rate limiting, a consistent error
contract, and the OpenRouter LLM config. The chatbot (Phase 5) and the
condition/value predictor (Phase 6) are added as routers on top of this.
"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .errors import ApiError, api_error_handler
from .routers import chat, health, predict, report, vehicles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("fixora")


def _warm_retriever() -> None:
    """Load the FAQ embedding model + build/cache the index once, so the first
    real chat request isn't slow. Runs in a background thread so startup is not
    blocked; falls back to keyword search if the ML stack is unavailable."""
    try:
        from .chat.knowledge import get_retriever

        get_retriever().search("warm up", k=1)
        logger.info("Retriever warmed and cached")
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Retriever warm-up skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm_retriever, daemon=True).start()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ApiError, api_error_handler)

    app.include_router(health.router)
    app.include_router(vehicles.router)
    app.include_router(chat.router)
    app.include_router(predict.router)
    app.include_router(report.router)
    return app


app = create_app()
