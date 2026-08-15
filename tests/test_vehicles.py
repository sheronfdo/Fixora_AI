from .conftest import auth

VEHICLE = {
    "id": "veh-1",
    "owner_id": "owner-1",
    "registration_number": "WP CAB-4521",
    "make": {"name": "Toyota", "is_luxury": False},
    "model": {"name": "Axio"},
    "year_of_manufacture": 2019,
    "engine_type": "Hybrid",
    "transmission": "CVT",
    "current_mileage": 96000,
}


def test_owner_can_read_vehicle(client, with_vehicles):
    with_vehicles({"veh-1": VEHICLE})
    r = client.get("/api/vehicles/veh-1", headers=auth("owner-1"))
    assert r.status_code == 200
    body = r.json()
    assert body["make"] == "Toyota"
    assert body["service_record_count"] == 0


def test_foreign_vehicle_forbidden(client, with_vehicles):
    with_vehicles({"veh-1": VEHICLE})
    r = client.get("/api/vehicles/veh-1", headers=auth("someone-else"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_missing_vehicle_not_found(client, with_vehicles):
    with_vehicles({})
    r = client.get("/api/vehicles/veh-1", headers=auth("owner-1"))
    assert r.status_code == 404


def test_vehicle_requires_auth(client, with_vehicles):
    with_vehicles({"veh-1": VEHICLE})
    r = client.get("/api/vehicles/veh-1")
    assert r.status_code == 401
