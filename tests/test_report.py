"""Vehicle report endpoint — Stage 2 mocked, so no LLM call."""
from datetime import datetime, timedelta, timezone

from app.data import get_data

from .conftest import FakeData, auth

MK, MD = "make-1", "model-1"
MOCK_S2 = {
    "condition_adjustment": -4.0, "subsystem_adjustments": {},
    "factors": [{"record_id": "r1", "observation": "oil seep",
                 "direction": "negative", "weight": "moderate"}],
    "value_adjust_pct": -2.0, "insights": "Solid history.",
    "recommendations": ["Fix the oil seep."], "llm_adjusted": True,
}


def _records():
    now = datetime.now(timezone.utc)
    return [
        {"id": "r1", "serviced_at": (now - timedelta(days=400)).isoformat(),
         "severity": "Moderate", "work_performed": "Brake pads",
         "inspection_notes": "oil seep noted", "odometer_reading": 80000,
         "labour_cost": 5000, "employees": {"full_name": "Kamal"},
         "service_parts": [{"part_name": "Front pads", "quantity": 1}]},
        {"id": "r2", "serviced_at": (now - timedelta(days=60)).isoformat(),
         "severity": "Routine", "work_performed": "Oil change",
         "inspection_notes": "", "odometer_reading": 96000,
         "labour_cost": 3500, "employees": {"full_name": "Sunil"},
         "service_parts": []},
    ]


def _vehicle():
    return {"id": "v1", "owner_id": "owner-1", "make_id": MK, "model_id": MD,
            "year_of_manufacture": 2019, "current_mileage": 96000,
            "registration_number": "WP CAB-4521",
            "make": {"name": "Toyota", "is_luxury": False}, "model": {"name": "Axio"}}


def _install(client, monkeypatch):
    fake = FakeData({"v1": _vehicle()}, records={"v1": _records()},
                    baselines={(MK, MD, 2019): {"base_price_lkr": 12500000}})
    client.app.dependency_overrides[get_data] = lambda: fake
    monkeypatch.setattr("app.predict.engine.assess", lambda baseline, records: MOCK_S2)
    return fake


def test_report_payload_complete(client, monkeypatch):
    _install(client, monkeypatch)
    r = client.post("/api/vehicle-report/v1", headers=auth("owner-1"))
    assert r.status_code == 200
    body = r.json()

    assert body["vehicle"]["registration"] == "WP CAB-4521"
    assert body["condition"]["final_score"] > 0
    assert body["value"]["sufficient_data"] is True
    assert len(body["service_history"]) == 2
    assert body["service_history"][0]["mechanic"] == "Kamal"
    assert body["service_history"][0]["parts"][0]["name"] == "Front pads"
    assert "not a certified valuation" in body["disclaimer"].lower() or \
           "certified valuation" in body["disclaimer"].lower()


def test_report_foreign_forbidden(client, monkeypatch):
    _install(client, monkeypatch)
    r = client.post("/api/vehicle-report/v1", headers=auth("intruder"))
    assert r.status_code == 403


def test_report_requires_auth(client, monkeypatch):
    _install(client, monkeypatch)
    r = client.post("/api/vehicle-report/v1")
    assert r.status_code == 401
