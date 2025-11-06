# Changelog

All notable changes to this project are documented in this file.

Versioning scheme:
- Versions follow semantic versioning for stable releases (1.0.0+) and `0.<phase>.<minor>` for development milestones.
- Each tagged version represents the completion of a documented milestone.

## 1.0.0 — Production Release: Complete Music Downloader Application

This major release marks the completion of the music downloader application with a complete, production-ready feature set including advanced ranking, track management, and cross-platform support.

### 🎯 Major Features

#### Advanced YouTube Search Ranking System
- **Unified Ranking Algorithm**: Complete refactor of scoring system using new `RankingService` with configurable parameters
- **Comprehensive Scoring**: Multi-factor scoring including artist matching, title matching, duration proximity, and extended version detection
- **Score Breakdown**: Detailed score breakdown API for transparency (artist, title, extended, duration, remaining tokens)
- **Test Coverage**: 52 test cases validating ranking behavior across diverse scenarios
- **Documentation**: Complete ranking specification in `docs/search_ranking.md` and implementation guide in `docs/ranking_implementation.md`
- **Configuration**: All ranking parameters centralized in `ranking_config.py` for easy tuning

#### Enhanced Track Management
- **Track Dates**: Added `release_date` and `spotify_added_at` fields to track model for comprehensive date tracking
- **Enriched API Endpoints**: New `/tracks/with_playlist_info` and `/candidates/enriched` endpoints with complete track metadata
- **Track Identities Endpoint**: Dedicated `/tracks/{id}/identities` endpoint for identity management
- **Simplified UI**: Track manager now displays 3 essential date columns (Spotify Added, Playlist Added, Downloaded)
- **Unified Track Detail Page**: Single page combining overview, identities, and candidates for better UX

#### Cross-Platform File Timestamp Management
- **Windows Support**: Native timestamp setting using `pywin32` for accurate file dates
- **macOS Support**: Uses `SetFile` command for precise timestamp control
- **Linux Compatibility**: Graceful fallback with best-effort timestamp setting
- **Automatic Detection**: Platform-specific logic automatically selected at runtime
- **Production Ready**: Ensures correct file dates across all deployment environments

#### Improved Frontend Experience
- **Responsive Audio Player**: Enhanced global audio player with better responsive design and footer integration
- **Candidates Panel Enhancements**: Complete track information display with score breakdown visualization
- **Track Search Response**: Refactored structure for cleaner data flow and improved performance
- **Logging Improvements**: Enhanced debugging with track info and search results logging
- **Frontend Dependencies**: Updated to latest stable versions

### 🐛 Bug Fixes
- **SPA Routing**: Fixed 404 errors when accessing routes directly or after OAuth redirects (Spotify callback)
- **Artist Normalization**: Improved handling of featured artist markers (`feat.`, `ft.`, `featuring`)
- **Token Matching**: Added exact token bonus and extra token penalty for more accurate scoring
- **Test Channel Data**: Updated YouTube search channel test data for consistency

### 🔧 Technical Improvements
- **Extractor Args**: Added resolution and retry profiles for yt-dlp configuration
- **Auto-Migration**: Enhanced database migration system for seamless schema updates
- **Test Infrastructure**: Comprehensive test suite with tasks for ranking algorithm validation
- **Code Refactoring**: Disabled old scoring system tests in favor of new unified ranking service
- **Git Cleanup**: Removed tracked frontend assets from Git index

### 📚 Documentation
- **Implementation Summary**: Complete documentation in `IMPLEMENTATION_SUMMARY.md`
- **Ranking Guide**: Detailed ranking implementation guide with architecture and scoring process
- **SPA Routing**: Technical documentation for SPA fallback mechanism in `docs/technical/spa_routing.md`
- **API Documentation**: Updated API docs with new endpoints and response structures

### 🧪 Testing
- **96 Tests Passing**: Comprehensive test coverage across all features
- **SPA Routing Tests**: 6 new tests for frontend routing behavior
- **Ranking Tests**: Complete test suite validating all ranking cases
- **Cross-Platform Tests**: Platform-specific timestamp functionality tests
- **Integration Tests**: End-to-end testing of track management workflows

### 🚀 Deployment
- **Docker Support**: Multi-stage Dockerfile with optimized build and runtime stages
- **Environment Configuration**: Improved settings management with Docker Compose support
- **Production Ready**: Tested and validated for production deployment on Linux servers
- **Cross-Platform**: Supports Windows, macOS, and Linux development and production environments

---

## Previous Development Releases

### 0.5.3 — Enhanced Scoring and Extractor Configuration
- Length-identical bonus scoring for YouTube search
- Extractor args resolution with retry profiles
- Global audio context refactoring

### 0.5.1 — Phase 5: Dockerfile and Multi-Stage Build (Step 5.1)
- Added multi-stage Dockerfile: builds frontend with Node 20, installs backend Python deps in a venv, and assembles a slim runtime with ffmpeg.
- Added .dockerignore to reduce build context and exclude local data.
- README updated with docker build/run instructions.

0.4.1 — Phase 4: Candidate Scoring Heuristics (Step 4.1)
- Backend: Enhanced YouTube scoring with fuzzy token match, extended-aware duration proximity, official channel bonuses, and keyword penalties (lyrics/live/cover/karaoke; mild for audio-only).
- API: Candidate responses include a `score_breakdown` (Text/Duration/Channel/Extended/Penalty, Total).
- Frontend: Candidates panel shows badges for breakdown and a Strict filter toggle (0.50/0.30) to reduce false positives by default.
- Tests: Added keyword penalty tests; channel bonus tests still pass.

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
