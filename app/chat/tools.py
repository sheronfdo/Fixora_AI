"""LangChain tools for the chatbot, scoped to one authenticated user.

Every tool is built inside `build_tools(data, user_id)` so it closes over the
caller's identity — a tool can only ever read that user's own data. Tools never
raise: they return friendly strings the model can relay.
"""
from __future__ import annotations

import json

from ..data import DataAccess
from .estimate import estimate_service


def build_tools(data: DataAccess, user_id: str):
    from langchain_core.tools import StructuredTool

    def _owned(vehicle_id: str) -> dict | None:
        v = data.get_vehicle(vehicle_id)
        if v and v.get("owner_id") == user_id:
            return v
        return None

    def get_my_vehicles() -> str:
        """List the current user's registered vehicles with their id, name,
        registration number and current mileage."""
        vehicles = data.get_my_vehicles(user_id)
        if not vehicles:
            return "The user has no vehicles in their garage yet."
        lines = []
        for v in vehicles:
            make = (v.get("make") or {}).get("name", "")
            model = (v.get("model") or {}).get("name", "")
            lines.append(
                f"- id={v['id']} | {v.get('year_of_manufacture','')} {make} {model} "
                f"| plate {v.get('registration_number','')} "
                f"| {v.get('current_mileage',0)} km "
                f"| {v.get('engine_type','')}/{v.get('transmission','')}"
            )
        return "\n".join(lines)

    def get_service_history(vehicle_id: str) -> str:
        """Return the service records for one of the user's vehicles."""
        if not _owned(vehicle_id):
            return "That vehicle is not in the user's garage."
        records = data.get_service_records(vehicle_id)
        if not records:
            return "No service records yet for this vehicle."
        out = []
        for r in records[:8]:
            parts = ", ".join(
                p.get("part_name", "") for p in (r.get("service_parts") or [])
            )
            out.append(
                f"- {r.get('serviced_at','')[:10]}: {r.get('work_performed','service')} "
                f"(severity {r.get('severity','Routine')}, {r.get('odometer_reading','?')} km)"
                + (f"; parts: {parts}" if parts else "")
            )
        return "\n".join(out)

    def get_next_service_due(vehicle_id: str) -> str:
        """Return the next recommended service (km and/or date) for a vehicle."""
        if not _owned(vehicle_id):
            return "That vehicle is not in the user's garage."
        due = data.get_next_service_due(vehicle_id)
        if not due:
            return "No next-service recommendation has been recorded yet."
        return (
            f"Next service due at "
            f"{due.get('next_service_due_km') or '—'} km"
            + (f" or by {due['next_service_due_date']}" if due.get("next_service_due_date") else "")
        )

    def get_service_estimate(vehicle_id: str, service_type: str) -> str:
        """Give an indicative LKR cost estimate for a service on a vehicle.
        service_type is like 'Oil Change', 'Brake Repair', 'Full Inspection'."""
        v = _owned(vehicle_id)
        if not v:
            return "That vehicle is not in the user's garage."
        pricing = data.get_pricing_config()
        return json.dumps(estimate_service(v, pricing, service_type))

    def get_booking_status() -> str:
        """Return the user's current active booking and its stage, if any."""
        b = data.get_active_booking(user_id)
        if not b:
            return "The user has no active booking right now."
        return (
            f"Active booking: {(b.get('services') or {}).get('name','service')} "
            f"for {(b.get('vehicles') or {}).get('name','vehicle')} — "
            f"status '{b.get('status')}', slot {b.get('time_slot','')}."
        )

    def get_vehicle_condition(vehicle_id: str) -> str:
        """Return the latest AI condition score and value range for a vehicle,
        if one has been generated."""
        if not _owned(vehicle_id):
            return "That vehicle is not in the user's garage."
        val = data.get_latest_valuation(vehicle_id)
        if not val:
            return "No AI condition report has been generated for this vehicle yet."
        return (
            f"Condition {val.get('condition_pct')}% ({val.get('band')}); "
            f"estimated value LKR {val.get('value_low_lkr')}–{val.get('value_high_lkr')}."
        )

    return [
        StructuredTool.from_function(get_my_vehicles),
        StructuredTool.from_function(get_service_history),
        StructuredTool.from_function(get_next_service_due),
        StructuredTool.from_function(get_service_estimate),
        StructuredTool.from_function(get_booking_status),
        StructuredTool.from_function(get_vehicle_condition),
    ]
