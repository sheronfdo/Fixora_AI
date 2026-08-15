from app.config import get_settings

from .conftest import auth

VEHICLE = {"id": "veh-1", "owner_id": "owner-1", "make": {}, "model": {}}


def test_rate_limit_trips(client, with_vehicles):
    with_vehicles({"veh-1": VEHICLE})
    limit = get_settings().rate_limit_requests
    h = auth("owner-1")

    # Up to the limit: allowed.
    for _ in range(limit):
        assert client.get("/api/vehicles/veh-1", headers=h).status_code == 200

    # One more: rejected.
    r = client.get("/api/vehicles/veh-1", headers=h)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
