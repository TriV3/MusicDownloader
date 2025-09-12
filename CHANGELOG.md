# Changelog

All notable changes to this project are documented in this file.

Versioning scheme:
- Release versions map directly to the Phase/Step numbers defined in `docs/specs.md`.
- Version format is `0.<phase>.<step>`. For example: Step 1.1 becomes version `0.1.1`; Step 0.5 becomes `0.0.5`.
- Each tagged version represents the completion of the corresponding Step.

Unreleased
- Planning and work in progress.

0.1.2 — Phase 1 / Step 1.2: TrackIdentity Endpoints
- Extended TrackIdentity model with fingerprint and timestamps.
- Added CRUD API `/api/v1/identities` with filters (track_id, has_fingerprint, created range).
- Auto creation of manual identity on track creation.
- Frontend: Basic Identities panel with list, select track, edit identity.
- Tests for identity CRUD, filters, and auto-create.

0.1.1 — Phase 1 / Step 1.1: Track Normalization Utilities
- Added normalization utilities to clean artists/title and extract flags (remix/edit, live, remaster).
- Added duration helpers for matching (tolerance and delta).
- New endpoint: `GET /api/v1/tracks/normalize/preview` to preview normalized output.
- Frontend: Added a simple Normalization Playground to try normalization in real-time.
- Tests: Unit tests for normalization logic and endpoint.

0.0.5 — Phase 0 / Step 0.5: Test Suite Baseline
- Added pytest with pytest-asyncio.
- Implemented shared in-memory SQLite setup for tests and app lifecycle fixtures.
- Added tests for health, CRUD, crypto, and mocked Spotify OAuth.

0.0.4 — Phase 0 / Step 0.4: Frontend Dev and Build Integration
- Vite dev server proxies `/api` to backend.
- Frontend uses relative API paths.
- Production build outputs to `backend/app/static` and is served by FastAPI.

0.0.3 — Phase 0 / Step 0.3: OAuth and Secret Management Foundation
- SECRET_KEY-based encryption for stored refresh tokens.
- Generic OAuth token storage endpoints.
- Spotify OAuth (PKCE) endpoints: authorize, callback, refresh.
- Environment variables loaded from `backend/.env` (or process env).

0.0.2 — Phase 0 / Step 0.2: Core Models and CRUD
- Added core entities: SourceAccount, Playlist, Track, TrackIdentity, PlaylistTrack, SearchCandidate, Download, LibraryFile, OAuthToken, OAuthState.
- CRUD endpoints for sources, playlists, and tracks.
- Pydantic schemas for request/response.

0.0.1 — Phase 0 / Step 0.1: API and Database Baseline
- FastAPI application with `/api` namespace and Swagger at `/api/docs`.
- Async SQLAlchemy with SQLite; auto table creation on startup.
- Health endpoint and CORS for local development.
- SPA static serving (Vite build) at `/` with fallback.
