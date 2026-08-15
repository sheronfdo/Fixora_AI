from .conftest import auth, make_token


def test_malformed_header_rejected(client):
    r = client.get("/api/me", headers={"Authorization": "NotBearer xyz"})
    assert r.status_code == 401


def test_expired_token_rejected(client):
    r = client.get("/api/me", headers=auth("user-1", exp_delta=-10))
    assert r.status_code == 401


def test_wrong_secret_rejected(client):
    token = make_token("user-1", secret="not-the-real-secret")
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_garbage_token_rejected(client):
    r = client.get("/api/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
