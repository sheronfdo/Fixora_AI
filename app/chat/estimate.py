"""Server-side service-cost estimate, mirroring the Flutter estimator.

Used by the chatbot's get_service_estimate tool. It uses sensible defaults
(Semi Synthetic oil; Good brakes unless the service is a brake repair) and is
explicitly indicative — the app's booking flow captures the exact inputs.
"""
from __future__ import annotations


def _num(pricing: dict, key: str, default: float) -> float:
    v = pricing.get(key)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def estimate_service(vehicle: dict, pricing: dict, service_type: str) -> dict:
    luxury = bool((vehicle.get("make") or {}).get("is_luxury"))
    mileage = int(vehicle.get("current_mileage") or 0)
    engine = vehicle.get("engine_type")
    trans = vehicle.get("transmission")
    service = (service_type or "").strip().lower()

    labour = _num(pricing, "luxury_labour", 6000) if luxury else _num(pricing, "normal_labour", 3500)
    luxury_fee = _num(pricing, "luxury_fee", 5000) if luxury else 0.0

    if mileage > 100000:
        mileage_charge = _num(pricing, "mileage_100k", 4000)
    elif mileage > 70000:
        mileage_charge = _num(pricing, "mileage_70k", 2500)
    elif mileage > 40000:
        mileage_charge = _num(pricing, "mileage_40k", 1500)
    else:
        mileage_charge = 0.0

    engine_fee = 0.0
    if engine == "Diesel":
        engine_fee = _num(pricing, "engine_diesel", 1500)
    elif engine == "Hybrid":
        engine_fee = _num(pricing, "engine_hybrid", 2000)
    elif engine == "Electric":
        engine_fee = _num(pricing, "engine_electric", 2500)
    trans_fee = _num(pricing, "transmission_auto", 1000) if trans in ("Automatic", "CVT") else 0.0
    drivetrain = engine_fee + trans_fee

    # Default consumables
    oil_price = _num(pricing, "oil_semi_luxury", 8500) if luxury else _num(pricing, "oil_semi_normal", 6000)

    if "brake" in service:
        brake = _num(pricing, "brake_moderate_luxury", 16000) if luxury else _num(pricing, "brake_moderate_normal", 10000)
        total = brake + labour + mileage_charge + luxury_fee + drivetrain
        assumption = "assuming moderate brake wear"
    elif "wash" in service:
        total = _num(pricing, "wash_luxury", 5000) if luxury else _num(pricing, "wash_normal", 2500)
        assumption = "standard wash"
    elif "inspection" in service:
        total = oil_price + labour + 3000 + mileage_charge + luxury_fee + drivetrain
        assumption = "full inspection with oil service"
    else:  # oil change / general
        total = oil_price + labour + mileage_charge + luxury_fee + drivetrain
        assumption = "assuming a semi-synthetic oil change"

    return {
        "service": service_type,
        "estimate_lkr": round(total),
        "assumption": assumption,
        "note": "Indicative only — book in the app for an exact estimate.",
    }
