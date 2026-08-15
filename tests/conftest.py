"""Test fixtures: env, minted Supabase-style JWTs, and a fake data layer."""
import os
import time

# Configure BEFORE importing the app (settings are cached at import).
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ENVIRONMENT", "test")

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.data import DataAccess, get_data  # noqa: E402
from app import rate_limit  # noqa: E402

get_settings.cache_clear()

TEST_SECRET = "test-secret"


def make_token(
    user_id: str,
    *,
    secret: str = TEST_SECRET,
    exp_delta: int = 3600,
    aud: str = "authenticated",
) -> str:
    payload = {
        "sub": user_id,
        "email": f"{user_id}@example.com",
        "role": "authenticated",
        "aud": aud,
        "exp": int(time.time()) + exp_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth(user_id: str, **kw) -> dict:
    return {"Authorization": f"Bearer {make_token(user_id, **kw)}"}


class FakeData(DataAccess):
    """In-memory stand-in for the Supabase data layer."""

    def __init__(self, vehicles: dict[str, dict]):
        self._vehicles = vehicles

    def get_vehicle(self, vehicle_id: str):
        return self._vehicles.get(vehicle_id)

    def get_service_records(self, vehicle_id: str):
        return []


@pytest.fixture
def client():
    rate_limit.reset()
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    rate_limit.reset()


@pytest.fixture
def with_vehicles():
    """Install a fake data layer with the given vehicles; returns a setter."""
    def _install(vehicles: dict[str, dict]):
        app.dependency_overrides[get_data] = lambda: FakeData(vehicles)
    return _install
