# Architecture

Overview
- Frontend
  - React + Vite dev server for development.
  - Built assets output to `backend/app/static` for production.
- Backend
  - FastAPI app, API under `/api/*`, Swagger at `/api/docs`.
  - SQLAlchemy 2.x Async with SQLite (aiosqlite driver).
  - Entities: SourceAccount, Playlist, Track, TrackIdentity, PlaylistTrack, SearchCandidate, Download, LibraryFile, OAuthToken, OAuthState.
  - OAuth: Spotify PKCE flow with encrypted refresh tokens.

Runtime topology
- Dev:
  - Frontend at http://localhost:5173 (Vite, proxy `/api` → http://localhost:8000).
  - Backend at http://localhost:8000.
- Prod-like:
  - Backend serves SPA at `/` from `backend/app/static`.
  - API remains under `/api/*`.

Folders (backend)
- backend/app/api/v1 — versioned routers
- backend/app/db/models — SQLAlchemy models
- backend/app/db/session.py — engine/session factory
- backend/app/schemas — Pydantic DTOs
- backend/app/utils/crypto.py — token encryption helpers
- backend/app/main.py — app wiring and static mount

Startup
- On startup, the app creates tables using SQLAlchemy metadata.
- Docs are exposed at `/api/docs` and `/api/redoc`.

Notes
- Ensure `DATABASE_URL` is set appropriately; default SQLite DB for dev (`music.db`).
- `SECRET_KEY` required to encrypt refresh tokens; dev fallback stores `"plain:"` (not recommended for production).
