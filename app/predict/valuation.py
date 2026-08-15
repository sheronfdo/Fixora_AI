"""Stage 1 — market-anchored value estimate.

The base price comes from real collected market data (`market_baseline_prices`),
never from the LLM. If there's no baseline row for the make/model/year we
decline rather than guess.
"""
from __future__ import annotations


def value_baseline(
    vehicle: dict,
    final_score: float,
    expected_km: float,
    baseline_row: dict | None,
    has_history: bool,
) -> dict:
    if not baseline_row or baseline_row.get("base_price_lkr") in (None, 0):
        return {"sufficient": False, "low": None, "high": None, "point": None}

    base = float(baseline_row["base_price_lkr"])
    mileage = int(vehicle.get("current_mileage") or 0)

    condition_multiplier = 0.70 + (final_score / 100) * 0.35        # 0.70 .. 1.05
    excess_km = max(0, mileage - expected_km)
    mileage_adjustment = min(1.05, max(0.80, 1 - (excess_km / 100000) * 0.15))
    history_premium = 1.03 if has_history else 1.00

    point = base * condition_multiplier * mileage_adjustment * history_premium
    return {
        "sufficient": True,
        "point": round(point),
        "low": round(point * 0.94),
        "high": round(point * 1.06),
    }
