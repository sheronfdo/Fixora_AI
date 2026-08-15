"""Vehicle endpoints — demonstrate the ownership guard and provide the
read foundation the Phase 6 predictor will reuse. Rate-limited + authenticated.
"""
from fastapi import APIRouter, Depends

from ..data import DataAccess, get_data
from ..rate_limit import rate_limit
from ..security import CurrentUser

router = APIRouter()


@router.get("/api/vehicles/{vehicle_id}")
def get_vehicle_summary(
    vehicle_id: str,
    user: CurrentUser = Depends(rate_limit),
    data: DataAccess = Depends(get_data),
):
    """Return a vehicle summary, but only if the caller owns it.

    Raises 404 if the vehicle does not exist, 403 if it belongs to someone
    else — the core ownership guard the AI features depend on.
    """
    v = data.require_owned_vehicle(vehicle_id, user.id)
    return {
        "id": v["id"],
        "registration_number": v.get("registration_number"),
        "make": (v.get("make") or {}).get("name"),
        "model": (v.get("model") or {}).get("name"),
        "year": v.get("year_of_manufacture"),
        "engine_type": v.get("engine_type"),
        "transmission": v.get("transmission"),
        "current_mileage": v.get("current_mileage"),
        "service_record_count": len(data.get_service_records(vehicle_id)),
    }
