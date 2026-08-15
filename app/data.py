"""Server-side data access via the Supabase service-role client.

Everything the AI service reads from the database goes through this layer,
so it is the single seam tests override (see tests/conftest.py) and the only
place the service-role key is used. That key must never reach a client.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from .config import get_settings
from .errors import forbidden, not_found

logger = logging.getLogger("fixora.data")


class DataAccess:
    """Thin wrapper over the Supabase Python client (service role)."""

    def __init__(self, client: Any):
        self._client = client

    # --- Vehicles -------------------------------------------------------
    def get_vehicle(self, vehicle_id: str) -> dict | None:
        res = (
            self._client.table("user_vehicles")
            .select("*, make:make_id(name, is_luxury), model:model_id(name)")
            .eq("id", vehicle_id)
            .maybe_single()
            .execute()
        )
        return res.data if res else None

    def require_owned_vehicle(self, vehicle_id: str, user_id: str) -> dict:
        """Return the vehicle, or raise 404 (missing) / 403 (not owner)."""
        vehicle = self.get_vehicle(vehicle_id)
        if vehicle is None:
            raise not_found("Vehicle not found")
        if vehicle.get("owner_id") != user_id:
            raise forbidden("This vehicle does not belong to you")
        return vehicle

    # --- Service history (used by Phase 5/6) ----------------------------
    def get_service_records(self, vehicle_id: str) -> list[dict]:
        res = (
            self._client.table("service_records")
            .select("*, service_parts(*)")
            .eq("vehicle_id", vehicle_id)
            .order("serviced_at", desc=True)
            .execute()
        )
        return res.data or []


@lru_cache
def _service_client():
    """Build the service-role Supabase client once."""
    from supabase import create_client  # imported lazily so tests need no network

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("Supabase service credentials are not configured")
    return create_client(settings.supabase_url, settings.supabase_service_key)


def get_data() -> DataAccess:
    """FastAPI dependency. Overridden in tests with a fake."""
    return DataAccess(_service_client())
