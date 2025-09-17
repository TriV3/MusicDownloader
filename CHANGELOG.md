# Changelog

All notable changes to this project are documented in this file.

Versioning scheme:
- Versions follow `0.<phase>.<minor>` and milestones are described in `docs/specs.md`.
- Each tagged version represents the completion of a documented milestone.

Unreleased
- Planning and work in progress.

0.3.4 — Phase 3: Spotify UI (Step 3.4)
- Frontend Playlists page implements Spotify connect (PKCE OAuth), discovery, selection, and sync triggers.
- Silent token refresh on load; shows connected status.
- Discover lists playlists with owner and snapshot; selection persists; Sync reports created/updated/linked summary.
- Wired into navbar and dev proxy; redirects back to `/playlists` after successful callback.

0.3.3 — Phase 3: Incremental Spotify Playlist Sync (Step 3.3)
- Incremental sync logic for `POST /api/v1/playlists/spotify/sync`.
- Uses Spotify playlist `snapshot_id` to skip unchanged playlists.
- Detects removals (deleted tracks) and deletes corresponding `PlaylistTrack` links.
- Updates positions for reordered items and preserves/sets `added_at` when newly available.
- Returns new summary fields per playlist: `links_removed`, `skipped` plus global `total_links_removed`.
- Added test `test_spotify_incremental_sync.py` covering initial sync, skipped sync, and changed snapshot with additions/removals.

0.3.2 — Phase 3: Spotify Playlist Sync
- API: `POST /api/v1/playlists/spotify/sync` to fetch tracks from selected Spotify playlists and upsert Tracks, Identities, and PlaylistTrack mappings.
- Idempotent: running the sync multiple times does not duplicate tracks or links.
- Frontend: Playlists page adds a "Sync selected" button with a compact summary of created/updated/linked counts.

0.3.1 — Phase 3: Spotify Playlist Discovery
- Added `selected` flag to Playlist model with auto-migration.
- API: `GET /api/v1/playlists/spotify/discover` to fetch playlists using stored Spotify OAuth token; optional `persist` to upsert.
- API: `POST /api/v1/playlists/spotify/select` to mark selected playlists (unselect others for the same account).
- API: Enhanced `/api/v1/playlists` with filters (`provider`, `account_id`, `selected`).
- Frontend: New Playlists page to discover and select playlists.
- Tests: Added coverage for discovery and selection with mocked Spotify API.

0.1.3 — Phase 1: SearchCandidate Endpoints + Enhancements (Track Manager, Auto Normalization, Track Deletion)
- Added CRUD API `/api/v1/candidates` with sorting (score desc, duration delta asc) and choose endpoint.
- Added computed `duration_delta_sec` in responses.
- Frontend: Candidates panel with track selection, sorting, choose action, manual add form.
- Tests: Candidate creation, sorting, choose uniqueness, deletion.
- Track creation no longer requires pre-computed normalized fields; backend auto-normalizes when omitted.
- Added Track Manager UI component: create tracks with live normalization preview and list existing tracks.
- Frontend refactored into modular components (NormalizationPlayground, TrackManager, IdentitiesPanel, CandidatesPanel).
- Added auto-normalization test to ensure normalized fields are populated and manual identity auto-created.
- Startup now performs a best-effort SQLite schema patch for legacy databases: adds missing `fingerprint`, `created_at`, `updated_at` columns to `track_identities` if absent (temporary until real migrations).
- Added DELETE `/api/v1/tracks/{id}` endpoint with manual cascade removal (identities, candidates, downloads, playlist links, library files).
- Frontend Track Manager: delete buttons per row + global event `tracks:changed` broadcast after create/delete.
- Other panels (Identities, Candidates) auto-refresh track list on `tracks:changed`.
- Extended CRUD test to cover track deletion and 404 verification.

0.1.2 — Phase 1: TrackIdentity Endpoints
- Extended TrackIdentity model with fingerprint and timestamps.
- Added CRUD API `/api/v1/identities` with filters (track_id, has_fingerprint, created range).
- Auto creation of manual identity on track creation.
- Frontend: Basic Identities panel with list, select track, edit identity.
- Tests for identity CRUD, filters, and auto-create.

0.1.1 — Phase 1: Track Normalization Utilities
- Added normalization utilities to clean artists/title and extract flags (remix/edit, live, remaster).
- Added duration helpers for matching (tolerance and delta).
- New endpoint: `GET /api/v1/tracks/normalize/preview` to preview normalized output.
- Frontend: Added a simple Normalization Playground to try normalization in real-time.
- Tests: Unit tests for normalization logic and endpoint.

0.0.5 — Phase 0: Test Suite Baseline
- Added pytest with pytest-asyncio.
- Implemented shared in-memory SQLite setup for tests and app lifecycle fixtures.
- Added tests for health, CRUD, crypto, and mocked Spotify OAuth.

0.0.4 — Phase 0: Frontend Dev and Build Integration
- Vite dev server proxies `/api` to backend.
- Frontend uses relative API paths.
- Production build outputs to `backend/app/static` and is served by FastAPI.

0.0.3 — Phase 0: OAuth and Secret Management Foundation
- SECRET_KEY-based encryption for stored refresh tokens.
- Generic OAuth token storage endpoints.
- Spotify OAuth (PKCE) endpoints: authorize, callback, refresh.
- Environment variables loaded from `backend/.env` (or process env).

0.0.2 — Phase 0: Core Models and CRUD
- Added core entities: SourceAccount, Playlist, Track, TrackIdentity, PlaylistTrack, SearchCandidate, Download, LibraryFile, OAuthToken, OAuthState.
- CRUD endpoints for sources, playlists, and tracks.
- Pydantic schemas for request/response.

0.0.1 — Phase 0: API and Database Baseline
- FastAPI application with `/api` namespace and Swagger at `/api/docs`.
- Async SQLAlchemy with SQLite; auto table creation on startup.
- Health endpoint and CORS for local development.
- SPA static serving (Vite build) at `/` with fallback.
