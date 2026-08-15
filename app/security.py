"""Supabase JWT verification and the current-user dependency."""
import logging
from dataclasses import dataclass

import jwt
from fastapi import Header

from .config import get_settings
from .errors import unauthorized

logger = logging.getLogger("fixora.security")


@dataclass
class CurrentUser:
    id: str
    email: str | None = None
    role: str | None = None


def decode_token(token: str) -> CurrentUser:
    """Verify a Supabase access token (HS256) and return the user.

    Supabase signs access tokens with the project's JWT secret. Verifying
    locally keeps every request fast and offline-testable. The audience for a
    signed-in user is 'authenticated'.
    """
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        # Misconfiguration — fail closed rather than trusting unverified tokens.
        logger.error("SUPABASE_JWT_SECRET is not set; cannot verify tokens")
        raise unauthorized("Server auth is not configured")

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
    except jwt.ExpiredSignatureError:
        raise unauthorized("Session expired")
    except jwt.InvalidTokenError as exc:
        logger.info("Rejected token: %s", exc)
        raise unauthorized("Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise unauthorized("Token missing subject")

    return CurrentUser(
        id=sub,
        email=payload.get("email"),
        role=payload.get("role"),
    )


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """FastAPI dependency: extract and verify the Bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    return decode_token(token)
