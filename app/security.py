"""Supabase JWT verification and the current-user dependency.

Supabase signs access tokens either with the legacy shared secret (HS256) or,
for newer projects, an asymmetric signing key (ES256/RS256). We support both:

- HS256  → verify locally with the project's JWT secret (fast, offline-testable).
- ES256/RS256 → verify against the project's public keys (JWKS), fetched and
  cached from `<supabase_url>/auth/v1/.well-known/jwks.json`.

The verification key is always chosen from the token's algorithm, so an attacker
cannot swap algorithms to bypass a key type.
"""
import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient
from fastapi import Header

from .config import get_settings
from .errors import ApiError, unauthorized

logger = logging.getLogger("fixora.security")

# Algorithms we accept. HS256 is symmetric (shared secret); the rest are
# asymmetric (verified via JWKS). Anything else is rejected.
_ASYMMETRIC_ALGS = {"ES256", "ES384", "ES512", "RS256", "RS384", "RS512"}
_ALLOWED_ALGS = {"HS256"} | _ASYMMETRIC_ALGS


@dataclass
class CurrentUser:
    id: str
    email: str | None = None
    role: str | None = None


@lru_cache
def _jwk_client(jwks_url: str) -> PyJWKClient:
    """One JWKS client per URL; it fetches and caches the public keys."""
    return PyJWKClient(jwks_url)


def _verification_key(token: str, alg: str) -> str:
    """Return the key to verify this token with, based on its algorithm."""
    settings = get_settings()

    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            logger.error("SUPABASE_JWT_SECRET is not set; cannot verify HS256 tokens")
            raise unauthorized("Server auth is not configured")
        return settings.supabase_jwt_secret

    # Asymmetric: fetch the matching public key from Supabase's JWKS.
    if not settings.supabase_url:
        logger.error("SUPABASE_URL is not set; cannot verify asymmetric tokens")
        raise unauthorized("Server auth is not configured")
    jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return _jwk_client(jwks_url).get_signing_key_from_jwt(token).key


def decode_token(token: str) -> CurrentUser:
    """Verify a Supabase access token (HS256 or asymmetric) and return the user."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid token")

    alg = header.get("alg", "")
    if alg not in _ALLOWED_ALGS:
        logger.info("Rejected token: algorithm %r not allowed", alg)
        raise unauthorized("Invalid token")

    try:
        key = _verification_key(token, alg)
        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience="authenticated",
            options={"verify_exp": True},
        )
    except ApiError:
        raise
    except jwt.ExpiredSignatureError:
        raise unauthorized("Session expired")
    except jwt.InvalidTokenError as exc:
        logger.info("Rejected token: %s", exc)
        raise unauthorized("Invalid token")
    except Exception as exc:  # JWKS fetch / crypto errors
        logger.warning("Token verification failed: %s", exc)
        raise unauthorized("Could not verify token")

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
