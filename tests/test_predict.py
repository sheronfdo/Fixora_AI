"""Endpoint tests for /api/predict-condition. Stage 2 (LLM) is mocked, so the
real formula + assembly + caching run without an LLM."""
from datetime import datetime, timedelta, timezone

from app.data import get_data

from .conftest import FakeData, auth

MK, MD = "make-1", "model-1"


def _records():
    now = datetime.now(timezone.utc)
    def rec(days, sev="Routine"):
        return {"id": f"r{days}", "serviced_at": (now - timedelta(days=days)).isoformat(),
                "severity": sev, "work_performed": "service", "inspection_notes": "",
                "service_parts": []}
    return [rec(1080), rec(900), rec(700), rec(400), rec(200, "Moderate"), rec(60)]


def _vehicle():
    return {"id": "v1", "owner_id": "owner-1", "make_id": MK, "model_id": MD,
            "year_of_manufacture": 2019, "current_mileage": 96000,
            "make": {"name": "Toyota", "is_luxury": False}, "model": {"name": "Axio"}}


MOCK_S2 = {
    "condition_adjustment": -5.0,
    "subsystem_adjustments": {},
    "factors": [{"record_id": "r60", "observation": "unresolved oil seep",
                 "direction": "negative", "weight": "moderate"}],
    "value_adjust_pct": -3.0,
    "insights": "Well serviced but an unresolved oil seep was noted.",
    "recommendations": ["Resolve the valve cover oil seep."],
    "llm_adjusted": True,
}


def _install(client, monkeypatch):
    fake = FakeData(
        {"v1": _vehicle()},
        records={"v1": _records()},
        baselines={(MK, MD, 2019): {"base_price_lkr": 12500000}},
    )
    client.app.dependency_overrides[get_data] = lambda: fake
    monkeypatch.setattr("app.predict.engine.assess", lambda baseline, records: MOCK_S2)
    return fake


def test_prediction_applies_llm_adjustment(client, monkeypatch):
    _install(client, monkeypatch)
    r = client.post("/api/predict-condition", json={"vehicle_id": "v1"}, headers=auth("owner-1"))
    assert r.status_code == 200
    body = r.json()

    cond = body["condition"]
    assert cond["llm_adjusted"] is True
    # final = baseline - 5 (the mocked adjustment), and strictly lower
    assert cond["final_score"] == round(cond["baseline_score"] - 5, 1)
    assert cond["final_score"] < cond["baseline_score"]
    assert body["llm_factors"][0]["record_id"] == "r60"
    assert body["value"]["sufficient_data"] is True
    assert body["value"]["low_lkr"] > 0
    assert body["cached"] is False


def test_foreign_vehicle_forbidden(client, monkeypatch):
    _install(client, monkeypatch)
    r = client.post("/api/predict-condition", json={"vehicle_id": "v1"}, headers=auth("intruder"))
    assert r.status_code == 403


def test_second_call_is_cached(client, monkeypatch):
    _install(client, monkeypatch)
    h = auth("owner-1")
    r1 = client.post("/api/predict-condition", json={"vehicle_id": "v1"}, headers=h)
    assert r1.json()["cached"] is False
    r2 = client.post("/api/predict-condition", json={"vehicle_id": "v1"}, headers=h)
    assert r2.json()["cached"] is True


def test_force_refresh_bypasses_cache(client, monkeypatch):
    _install(client, monkeypatch)
    h = auth("owner-1")
    client.post("/api/predict-condition", json={"vehicle_id": "v1"}, headers=h)
    r = client.post("/api/predict-condition",
                    json={"vehicle_id": "v1", "force_refresh": True}, headers=h)
    assert r.json()["cached"] is False


def test_insufficient_market_data(client, monkeypatch):
    fake = FakeData({"v1": _vehicle()}, records={"v1": _records()}, baselines={})
    client.app.dependency_overrides[get_data] = lambda: fake
    monkeypatch.setattr("app.predict.engine.assess", lambda baseline, records: MOCK_S2)
    r = client.post("/api/predict-condition", json={"vehicle_id": "v1"}, headers=auth("owner-1"))
    assert r.json()["value"]["sufficient_data"] is False
