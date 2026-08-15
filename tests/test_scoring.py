"""Stage 1 golden tests — the deterministic VCP baseline (report evidence)."""
from datetime import datetime, timedelta

from app.predict.scoring import band_for, compute_baseline

NOW = datetime(2026, 8, 15)


def _record(days_ago: int, severity="Routine", parts=None):
    return {
        "id": f"r{days_ago}",
        "serviced_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "severity": severity,
        "service_parts": parts or [],
    }


def test_worked_example_axio():
    """2019 Axio, 96,000 km, 6 services (5 routine + 1 moderate),
    first ~36 months ago, last 2 months ago → baseline 86.8, High, Excellent."""
    vehicle = {"id": "v", "year_of_manufacture": 2019, "current_mileage": 96000}
    records = [
        _record(1080),  # ~36 months ago (first)
        _record(900),
        _record(700),
        _record(400),
        _record(200, "Moderate"),
        _record(60),    # 2 months ago (last)
    ]
    b = compute_baseline(vehicle, records, NOW)
    assert b["confidence"] == "High"
    assert b["baseline_score"] == 86.8
    assert b["band"] == "Excellent"


def test_cold_start_uses_age_and_mileage_only():
    """New-ish car, no records → Low confidence, age+mileage only,
    NOT dragged to Poor."""
    vehicle = {"id": "v", "year_of_manufacture": 2021, "current_mileage": 60000}
    b = compute_baseline(vehicle, [], NOW)
    assert b["confidence"] == "Low"
    # age(5)->80, mileage(ratio 1.0)->85, weights .5/.5 -> 82.5
    assert b["baseline_score"] == 82.5
    assert b["band"] == "Good"


def test_old_neglected_scores_poor():
    vehicle = {"id": "v", "year_of_manufacture": 2011, "current_mileage": 280000}
    records = [_record(900, "Major")]  # 1 record ~30 months ago
    b = compute_baseline(vehicle, records, NOW)
    assert b["confidence"] == "Medium"
    assert b["baseline_score"] < 50
    assert b["band"] == "Poor"


def test_determinism():
    vehicle = {"id": "v", "year_of_manufacture": 2018, "current_mileage": 110000}
    records = [_record(400), _record(200, "Moderate"), _record(50)]
    scores = {compute_baseline(vehicle, records, NOW)["baseline_score"] for _ in range(10)}
    assert len(scores) == 1  # bit-identical every run


def test_bands():
    assert band_for(90) == "Excellent"
    assert band_for(75) == "Good"
    assert band_for(55) == "Fair"
    assert band_for(30) == "Poor"
