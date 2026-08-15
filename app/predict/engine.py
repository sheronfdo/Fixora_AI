"""Orchestrate the two-stage prediction into one auditable result."""
from __future__ import annotations

from datetime import datetime

from ..config import get_settings
from .llm_assess import assess
from .scoring import band_for, compute_baseline
from .valuation import value_baseline


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def predict(
    vehicle: dict,
    records: list[dict],
    baseline_row: dict | None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.utcnow()

    # Stage 1 — deterministic baseline
    b = compute_baseline(vehicle, records, now)

    # Stage 2 — bounded LLM adjustment (fail-safe → zeros)
    s2 = assess(b, records)

    final_score = round(_clamp(b["baseline_score"] + s2["condition_adjustment"], 0, 100), 1)
    band = band_for(final_score)

    subsystems = {}
    for sub, base in b["subsystem_baselines"].items():
        adj = float(s2["subsystem_adjustments"].get(sub, 0))
        subsystems[sub] = {
            "baseline": base,
            "adjustment": adj,
            "final": round(_clamp(base + adj, 0, 100), 1),
        }

    # Value — uses the FINAL condition score
    has_history = len(records) > 0
    vb = value_baseline(vehicle, final_score, b["expected_km"], baseline_row, has_history)
    if vb["sufficient"]:
        pct = float(s2["value_adjust_pct"])
        value = {
            "sufficient_data": True,
            "baseline_low_lkr": vb["low"],
            "baseline_high_lkr": vb["high"],
            "adjustment_pct": pct,
            "low_lkr": round(vb["low"] * (1 + pct / 100)),
            "high_lkr": round(vb["high"] * (1 + pct / 100)),
        }
    else:
        value = {
            "sufficient_data": False,
            "baseline_low_lkr": None, "baseline_high_lkr": None,
            "adjustment_pct": 0, "low_lkr": None, "high_lkr": None,
        }

    settings = get_settings()
    model_version = (
        f"vcp-v1.0+{settings.openrouter_model}" if s2["llm_adjusted"] else "vcp-v1.0"
    )

    return {
        "vehicle_id": vehicle["id"],
        "condition": {
            "baseline_score": b["baseline_score"],
            "baseline_breakdown": b["breakdown"],
            "llm_adjustment": s2["condition_adjustment"],
            "llm_adjusted": s2["llm_adjusted"],
            "final_score": final_score,
            "band": band,
            "confidence": b["confidence"],
        },
        "llm_factors": s2["factors"],
        "subsystems": subsystems,
        "value": value,
        "insights": s2["insights"],
        "recommendations": s2["recommendations"],
        "inputs_snapshot": {
            "age_years": b["age_years"],
            "mileage": int(vehicle.get("current_mileage") or 0),
            "records": b["record_count"],
            "expected_km": b["expected_km"],
        },
        "model_version": model_version,
        "generated_at": now.isoformat() + "Z",
    }


def row_to_response(row: dict) -> dict:
    """Rebuild the API response from a stored vehicle_valuations row (cache hit)."""
    base = row.get("subsystem_baselines") or {}
    adj = row.get("llm_subsystem_adj") or {}
    fin = row.get("subsystem_scores") or {}
    subsystems = {
        k: {"baseline": base.get(k), "adjustment": adj.get(k, 0), "final": fin.get(k)}
        for k in fin
    }
    return {
        "vehicle_id": row.get("vehicle_id"),
        "condition": {
            "baseline_score": row.get("baseline_score"),
            "baseline_breakdown": row.get("baseline_breakdown"),
            "llm_adjustment": row.get("llm_adjustment"),
            "llm_adjusted": row.get("llm_adjusted"),
            "final_score": row.get("condition_pct"),
            "band": row.get("band"),
            "confidence": row.get("confidence"),
        },
        "llm_factors": row.get("llm_factors") or [],
        "subsystems": subsystems,
        "value": {
            "sufficient_data": row.get("value_sufficient"),
            "baseline_low_lkr": row.get("value_baseline_low"),
            "baseline_high_lkr": row.get("value_baseline_high"),
            "adjustment_pct": row.get("value_adjust_pct"),
            "low_lkr": row.get("value_low_lkr"),
            "high_lkr": row.get("value_high_lkr"),
        },
        "insights": row.get("insights") or "",
        "recommendations": row.get("recommendations") or [],
        "inputs_snapshot": row.get("inputs_snapshot") or {},
        "model_version": row.get("model_version"),
        "generated_at": row.get("generated_at"),
        "cached": True,
    }


def to_db_row(result: dict) -> dict:
    """Flatten a prediction into a vehicle_valuations insert payload."""
    c = result["condition"]
    v = result["value"]
    return {
        "vehicle_id": result["vehicle_id"],
        "baseline_score": c["baseline_score"],
        "baseline_breakdown": c["baseline_breakdown"],
        "subsystem_baselines": {k: v2["baseline"] for k, v2 in result["subsystems"].items()},
        "llm_adjustment": c["llm_adjustment"],
        "llm_subsystem_adj": {k: v2["adjustment"] for k, v2 in result["subsystems"].items()},
        "llm_factors": result["llm_factors"],
        "llm_adjusted": c["llm_adjusted"],
        "condition_pct": c["final_score"],
        "band": c["band"],
        "confidence": c["confidence"],
        "subsystem_scores": {k: v2["final"] for k, v2 in result["subsystems"].items()},
        "value_baseline_low": v["baseline_low_lkr"],
        "value_baseline_high": v["baseline_high_lkr"],
        "value_adjust_pct": v["adjustment_pct"],
        "value_low_lkr": v["low_lkr"],
        "value_high_lkr": v["high_lkr"],
        "value_sufficient": v["sufficient_data"],
        "insights": result["insights"],
        "recommendations": result["recommendations"],
        "inputs_snapshot": result["inputs_snapshot"],
        "model_version": result["model_version"],
    }
