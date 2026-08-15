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

    def get_my_vehicles(self, user_id: str) -> list[dict]:
        res = (
            self._client.table("user_vehicles")
            .select("*, make:make_id(name, is_luxury), model:model_id(name)")
            .eq("owner_id", user_id)
            .eq("is_active", True)
            .order("is_default", desc=True)
            .execute()
        )
        return res.data or []

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

    def get_service_history_detailed(self, vehicle_id: str) -> list[dict]:
        """Chronological history with parts and the mechanic's name, for the report."""
        res = (
            self._client.table("service_records")
            .select("*, service_parts(*), employees:mechanic_id(full_name)")
            .eq("vehicle_id", vehicle_id)
            .order("serviced_at", desc=False)
            .execute()
        )
        return res.data or []

    def get_next_service_due(self, vehicle_id: str) -> dict | None:
        """The next-service recommendation from the most recent job card."""
        records = self.get_service_records(vehicle_id)
        for r in records:
            if r.get("next_service_due_km") or r.get("next_service_due_date"):
                return {
                    "next_service_due_km": r.get("next_service_due_km"),
                    "next_service_due_date": r.get("next_service_due_date"),
                    "as_of": r.get("serviced_at"),
                }
        return None

    def get_active_booking(self, user_id: str) -> dict | None:
        res = (
            self._client.table("bookings")
            .select("*, services:service_id(name), vehicles:vehicle_id(name)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        b = rows[0]
        if b.get("status") in ("Completed", "Cancelled"):
            return None
        return b

    def get_pricing_config(self) -> dict:
        res = self._client.table("pricing_config").select("key_name, value").execute()
        return {r["key_name"]: r["value"] for r in (res.data or [])}

    def get_market_baseline(self, make_id, model_id, year) -> dict | None:
        try:
            res = (
                self._client.table("market_baseline_prices")
                .select("base_price_lkr, sample_size, source")
                .eq("make_id", make_id)
                .eq("model_id", model_id)
                .eq("year", year)
                .maybe_single()
                .execute()
            )
            return res.data if res else None
        except Exception:
            return None

    def save_valuation(self, row: dict) -> None:
        self._client.table("vehicle_valuations").insert(row).execute()

    def get_recent_valuation(self, vehicle_id: str) -> dict | None:
        """The full latest valuation row (for the 24h cache)."""
        try:
            res = (
                self._client.table("vehicle_valuations")
                .select("*")
                .eq("vehicle_id", vehicle_id)
                .order("generated_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def get_latest_valuation(self, vehicle_id: str) -> dict | None:
        """Latest cached AI valuation. Graceful if the table doesn't exist yet."""
        try:
            res = (
                self._client.table("vehicle_valuations")
                .select("condition_pct, band, value_low_lkr, value_high_lkr, generated_at")
                .eq("vehicle_id", vehicle_id)
                .order("generated_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    # --- Chat persistence ----------------------------------------------
    def save_chat_message(self, user_id: str, conversation_id: str, role: str, content: str) -> None:
        self._client.table("chat_messages").insert({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
        }).execute()

    def get_recent_messages(self, conversation_id: str, limit: int = 20) -> list[dict]:
        res = (
            self._client.table("chat_messages")
            .select("role, content, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = res.data or []
        rows.reverse()  # chronological
        return rows


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
