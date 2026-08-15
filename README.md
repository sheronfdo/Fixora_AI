# Fixora AI Service

Python **FastAPI** microservice — the third tier of Fixora. It hosts the AI
features (chatbot in Phase 5, condition & value prediction in Phase 6) behind a
secure boundary: it verifies Supabase access tokens, enforces that a user can
only touch their own data, rate-limits per user, and talks to LLMs through
**OpenRouter** (one OpenAI-compatible endpoint routing to many models).

## Endpoints (Phase 4)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/health` | public | Uptime + config (no LLM call) |
| GET | `/api/me` | Bearer | Echo the verified user — token sanity check |
| GET | `/api/vehicles/{id}` | Bearer + owner | Vehicle summary; **403** if not owner, **404** if missing |

Error envelope: `{ "error": { "code": "...", "message": "..." } }` with
`401 / 403 / 404 / 422 / 429 / 503`.

## Local setup

```bash
cd service_stationAI
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in Supabase + OpenRouter values
uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

`SUPABASE_JWT_SECRET` is in Supabase → Project Settings → API → JWT Secret.
The service verifies access tokens locally with it (HS256), so no network call
is needed per request.

## Tests

```bash
pytest
```

Covers: health, JWT verification (missing / malformed / expired / wrong-secret),
the ownership guard (owner 200, foreign 403, missing 404, no-token 401), and
rate limiting. The data layer is faked, so tests need no database or network.

## Deploy

- **Render:** use `render.yaml` (Docker) — set the secret env vars in the dashboard.
- **Railway:** point at the `Dockerfile`; Railway injects `$PORT`.

Set env vars from `.env.example`. The **service-role key lives only here** —
never in the Flutter or React clients.

## Switching LLM models

Change `OPENROUTER_MODEL` (e.g. `anthropic/claude-3.5-sonnet`,
`google/gemini-flash-1.5`, `openai/gpt-4o-mini`). No code change. Set a spend
cap on the OpenRouter key to bound cost.
