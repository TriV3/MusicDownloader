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
