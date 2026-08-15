"""Stage 1 — deterministic Vehicle Condition Percentage (VCP).

Pure functions, no LLM, no I/O. Given the same inputs they return a
bit-identical score, so they are unit-testable and the methodology is
defensible. See docs/PROJECT_PLAN.md §8.
"""
from __future__ import annotations

from datetime import datetime

ANNUAL_KM_BASELINE = 12000  # Sri-Lanka-tuned expected km/year
SEVERITY_WEIGHT = {"Routine": 1, "Moderate": 3, "Major": 8}
BANDS = [(85, "Excellent"), (70, "Good"), (50, "Fair"), (0, "Poor")]

SUBSYSTEMS = ["Engine", "Brakes", "Transmission", "Suspension"]
# Map a part's `subsystem` tag onto one of the four reported sub-systems.
_PART_TO_SUBSYSTEM = {
    "Engine": "Engine",
    "Brakes": "Brakes",
    "Transmission": "Transmission",
    "Suspension": "Suspension",
    "Body": "Suspension",
    "Electrical": "Engine",
    "Other": "Engine",
}


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _months_between(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).days / 30.4375)


def band_for(score: float) -> str:
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return "Poor"


# --- component scores (each 0..100) ------------------------------------

def age_score(age_years: int) -> float:
    return max(0.0, 100.0 - age_years * 4)


def mileage_score(current_mileage: int, expected_km: float) -> float:
    ratio = current_mileage / max(expected_km, 1)
    if ratio <= 0.7:
        return 100.0
    if ratio <= 1.0:
        return 100.0 - (ratio - 0.7) * 50
    if ratio <= 1.5:
        return 85.0 - (ratio - 1.0) * 50
    return max(30.0, 60.0 - (ratio - 1.5) * 40)


def service_adherence_score(actual_services: int, tracked_years: float) -> float:
    expected = max(1, round(tracked_years * 2))
    return min(100.0, (actual_services / expected) * 100)


def repair_severity_score(records: list[dict]) -> float:
    penalty = sum(SEVERITY_WEIGHT.get(r.get("severity", "Routine"), 1) for r in records)
    return max(20.0, 100.0 - penalty * 2)


def recency_score(months_since_last: float) -> float:
    m = months_since_last
    if m <= 6:
        return 100.0
    if m <= 12:
        return 100.0 - (m - 6) * 5
    if m <= 24:
        return 70.0 - (m - 12) * 2.5
    return 30.0


# --- confidence --------------------------------------------------------

def confidence_for(num_records: int, tracked_months: float) -> str:
    if num_records >= 3 and tracked_months >= 12:
        return "High"
    if num_records >= 1 and tracked_months >= 3:
        return "Medium"
    return "Low"


# --- sub-system baselines ---------------------------------------------

def subsystem_baselines(records: list[dict], now: datetime, overall: float) -> dict:
    scores: dict[str, float] = {}
    for sub in SUBSYSTEMS:
        relevant = []
        for r in records:
            subs = {
                _PART_TO_SUBSYSTEM.get(p.get("subsystem", "Other"), "Engine")
                for p in (r.get("service_parts") or [])
            }
            if sub in subs:
                relevant.append(r)
        if not relevant:
            # No specific evidence → track the overall condition.
            scores[sub] = round(overall, 1)
            continue
        penalty = sum(SEVERITY_WEIGHT.get(r.get("severity", "Routine"), 1) for r in relevant)
        recent = any(
            (_parse(r.get("serviced_at")) and _months_between(now, _parse(r["serviced_at"])) <= 12)
            for r in relevant
        )
        score = 80.0 - penalty * 2 + (15.0 if recent else 0.0)
        scores[sub] = round(max(20.0, min(100.0, score)), 1)
    return scores


# --- the baseline ------------------------------------------------------

def compute_baseline(vehicle: dict, records: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    year = int(vehicle.get("year_of_manufacture") or now.year)
    age = max(0, now.year - year)
    mileage = int(vehicle.get("current_mileage") or 0)
    expected_km = age * ANNUAL_KM_BASELINE

    times = sorted(t for t in (_parse(r.get("serviced_at")) for r in records) if t)
    tracked_months = _months_between(now, times[0]) if times else 0.0
    tracked_years = tracked_months / 12
    months_since_last = _months_between(now, times[-1]) if times else 999.0

    conf = confidence_for(len(records), tracked_months)

    comp = {
        "age": round(age_score(age), 1),
        "mileage": round(mileage_score(mileage, expected_km), 1),
        "service_adherence": round(service_adherence_score(len(records), tracked_years), 1),
        "repair_severity": round(repair_severity_score(records), 1),
        "recency": round(recency_score(months_since_last), 1),
    }

    if conf == "Low":
        # Thin history → age & mileage only (the always-known signals).
        weights = {"age": 0.5, "mileage": 0.5, "service_adherence": 0.0,
                   "repair_severity": 0.0, "recency": 0.0}
    else:
        weights = {"age": 0.20, "mileage": 0.20, "service_adherence": 0.25,
                   "repair_severity": 0.20, "recency": 0.15}

    baseline = round(sum(weights[k] * comp[k] for k in comp), 1)

    return {
        "baseline_score": baseline,
        "breakdown": comp,
        "weights": weights,
        "confidence": conf,
        "band": band_for(baseline),
        "subsystem_baselines": subsystem_baselines(records, now, baseline),
        "age_years": age,
        "expected_km": expected_km,
        "record_count": len(records),
    }
