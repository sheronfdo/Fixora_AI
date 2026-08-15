"""Chat endpoint tests — the LLM agent is mocked, so no OpenRouter call."""
from app.chat.agent import SYSTEM_PROMPT
from app.data import get_data

from .conftest import FakeData, auth


def test_chat_requires_auth(client):
    r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 401


def test_chat_returns_reply_and_persists(client, monkeypatch):
    fake = FakeData({})
    client.app.dependency_overrides[get_data] = lambda: fake

    monkeypatch.setattr(
        "app.routers.chat.run_chat",
        lambda **kw: ("Your next service is due at 90,000 km.", ["service_intervals:x"]),
    )

    r = client.post(
        "/api/chat",
        json={"message": "When is my next service due?"},
        headers=auth("owner-1"),
    )
    assert r.status_code == 200
    body = r.json()
    assert "90,000 km" in body["reply"]
    assert body["conversation_id"]
    assert body["sources"] == ["service_intervals:x"]

    # user + assistant messages persisted
    roles = [m["role"] for m in fake.messages]
    assert roles == ["user", "assistant"]


def test_chat_conversation_id_is_reused(client, monkeypatch):
    fake = FakeData({})
    client.app.dependency_overrides[get_data] = lambda: fake
    monkeypatch.setattr(
        "app.routers.chat.run_chat", lambda **kw: ("ok", [])
    )

    r1 = client.post("/api/chat", json={"message": "hi"}, headers=auth("u"))
    cid = r1.json()["conversation_id"]
    r2 = client.post(
        "/api/chat",
        json={"message": "again", "conversation_id": cid},
        headers=auth("u"),
    )
    assert r2.json()["conversation_id"] == cid
    assert len(fake.messages) == 4  # 2 turns x (user+assistant)


def test_safety_guardrail_present_in_prompt():
    p = SYSTEM_PROMPT.lower()
    assert "brakes" in p and "steering" in p and "airbags" in p
    assert "never invent" in p
    assert "lkr" in p
