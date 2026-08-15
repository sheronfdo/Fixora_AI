"""Public health check and an authenticated identity echo."""
from fastapi import APIRouter, Depends

from ..config import get_settings
from ..llm import llm_configured
from ..security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/api/health")
def health():
    """Public — used for uptime checks. Reports config, makes no LLM call."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.version,
        "environment": settings.environment,
        "llm": settings.openrouter_model if llm_configured() else None,
    }


@router.get("/api/me")
def me(user: CurrentUser = Depends(get_current_user)):
    """Authenticated — lets the client verify its token reaches the service."""
    return {"id": user.id, "email": user.email, "role": user.role}
