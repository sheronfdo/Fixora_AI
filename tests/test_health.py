from .conftest import auth


def test_health_is_public_and_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_me_requires_token(client):
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_me_with_valid_token(client):
    r = client.get("/api/me", headers=auth("user-123"))
    assert r.status_code == 200
    assert r.json()["id"] == "user-123"
