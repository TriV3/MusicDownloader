## Service meta

- Info: `GET /api/v1/info` → `{ name, version }`
  - Name and version are defined once in `backend/app/app_meta.py` and injected into settings.

# API Overview

Base URLs
- API root: `/api`
- OpenAPI JSON: `/api/openapi.json`
- Swagger UI: `/api/docs`
- Redoc: `/api/redoc`
- Versioned routes: `/api/v1/...`

Conventions
- JSON in/out.
- HTTP status codes: 2xx success, 4xx client errors, 5xx server errors.
- Pagination and filtering to be added on listing endpoints.

Current endpoints (v1)
- GET `/api/v1/health` — returns API status.
- Sources (accounts):
  - GET `/api/v1/sources/accounts`
  - POST `/api/v1/sources/accounts`
- Playlists:
  - GET `/api/v1/playlists/`
  - POST `/api/v1/playlists/`
- Tracks:
  - GET `/api/v1/tracks/`
  - POST `/api/v1/tracks/`
  - GET `/api/v1/tracks/{id}`
  - PUT `/api/v1/tracks/{id}`
  - DELETE `/api/v1/tracks/{id}`
  - GET `/api/v1/tracks/{id}/youtube/search` — Search YouTube for candidates; supports `prefer_extended`, `persist`, `limit`
  - POST `/api/v1/tracks/{id}/cover/refresh` — Refresh cover using Spotify album art if available, otherwise chosen YouTube thumbnail
- OAuth (generic):
  - GET `/api/v1/oauth/tokens`
  - POST `/api/v1/oauth/tokens`
- OAuth (Spotify):
  - GET `/api/v1/oauth/spotify/authorize?account_id=...&redirect_to=...`
  - GET `/api/v1/oauth/spotify/callback?code=...&state=...`
  - POST `/api/v1/oauth/spotify/refresh?account_id=...`


Configuration
- Environment variables are loaded from `backend/.env` (via python-dotenv) and can be overridden by the process environment.
- Required for Spotify endpoints:
  - `SPOTIFY_CLIENT_ID`
  - `SPOTIFY_CLIENT_SECRET`
  - `SPOTIFY_REDIRECT_URI`
- Recommended:
  - `SECRET_KEY` for encrypting refresh tokens

Versioning
- Breaking API changes require bumping to `/api/v2` and updating docs/tests accordingly.

Testing
- Tests use in-memory SQLite via `DATABASE_URL` and `httpx.AsyncClient` mounted to the FastAPI app.
- See `backend/tests` for examples.

## YouTube search and scoring

Scoring combines:
- Text similarity between normalized artists+title and the YouTube title
- Duration proximity bonus (up to +0.25 for exact match, linear decay to 0 at ~12s delta)
- Extended/Club Mix bonus (+0.15 when `prefer_extended=true` and title indicates extended/club)
- Official channel bonus (+0.30 for official-looking channels such as VEVO, Official, or "- Topic"; +0.20 extra when the channel matches the primary artist name; capped at +0.50)
- Small penalties when primary artist is missing from title or important tokens are unmatched

Results are sorted by score desc then id asc for stability.
