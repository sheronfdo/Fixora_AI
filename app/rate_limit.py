"""Per-user in-memory sliding-window rate limiter.

Fine for a single-instance deployment (this project). For a horizontally
scaled deployment, swap the in-process store for Redis.
"""
import time
from collections import defaultdict, deque

from fastapi import Depends

from .config import get_settings
from .errors import rate_limited
from .security import CurrentUser, get_current_user

_hits: dict[str, deque[float]] = defaultdict(deque)


def _check(user_id: str) -> None:
    settings = get_settings()
    window = settings.rate_limit_window_seconds
    limit = settings.rate_limit_requests
    now = time.monotonic()

    q = _hits[user_id]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        raise rate_limited(f"Rate limit exceeded ({limit}/{window}s)")
    q.append(now)


def rate_limit(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency: enforce the per-user limit, then pass the user through."""
    _check(user.id)
    return user


def reset() -> None:
    """Test helper — clear all counters."""
    _hits.clear()
