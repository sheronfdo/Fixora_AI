"""POST /api/predict-condition — the two-stage hybrid condition & value."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..data import DataAccess, get_data
from ..predict.engine import predict, row_to_response, to_db_row
from ..rate_limit import rate_limit
from ..security import CurrentUser

logger = logging.getLogger("fixora.predict")
router = APIRouter()

CACHE_TTL = timedelta(hours=24)


class PredictRequest(BaseModel):
    vehicle_id: str
    force_refresh: bool = False


def _is_fresh(generated_at) -> bool:
    try:
        ts = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts < CACHE_TTL
    except (ValueError, TypeError):
        return False


@router.post("/api/predict-condition")
def predict_condition(
    body: PredictRequest,
    user: CurrentUser = Depends(rate_limit),
    data: DataAccess = Depends(get_data),
):
    vehicle = data.require_owned_vehicle(body.vehicle_id, user.id)  # 403 / 404

    # 24h cache unless a refresh is forced.
    if not body.force_refresh:
        recent = data.get_recent_valuation(body.vehicle_id)
        if recent and _is_fresh(recent.get("generated_at")):
            return row_to_response(recent)

    records = data.get_service_records(body.vehicle_id)

    baseline_row = None
    if vehicle.get("make_id") and vehicle.get("model_id") and vehicle.get("year_of_manufacture"):
        baseline_row = data.get_market_baseline(
            vehicle["make_id"], vehicle["model_id"], vehicle["year_of_manufacture"]
        )

    result = predict(vehicle, records, baseline_row)

    try:
        data.save_valuation(to_db_row(result))
    except Exception:  # caching is best-effort; still return the result
        logger.exception("Could not cache valuation")

    result["cached"] = False
    return result
