"""Fixora AI Service — FastAPI application factory.

Phase 4 delivers the secure foundation: health check, Supabase JWT
verification, the vehicle ownership guard, rate limiting, a consistent error
contract, and the OpenRouter LLM config. The chatbot (Phase 5) and the
condition/value predictor (Phase 6) are added as routers on top of this.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .errors import ApiError, api_error_handler
from .routers import chat, health, predict, vehicles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version)

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
    return app


app = create_app()
