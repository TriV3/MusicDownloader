# Music Downloader — Phased Delivery Plan

Note on versioning:
- Each Step completion is released as version `0.<phase>.<step>`. For example, Step 1.1 → version `0.1.1`, Step 0.5 → `0.0.5`.
- See `CHANGELOG.md` at the repo root for the list of released steps.

## Phase 0 — Baseline (existing)

### Step 0.1: API and Database Baseline
- FastAPI application with `/api` namespace and Swagger at `/api/docs`
- Async SQLAlchemy with SQLite; auto table creation on startup
- Health endpoint and CORS for local development
- SPA static serving (Vite build) at `/` with fallback

**Validation Criteria:**
1. `GET /api/v1/health` returns 200 with status JSON
2. Database file initializes or in-memory tables are created at startup
3. Vite build placed under `backend/app/static` is served at `/`
4. Swagger UI loads at `/api/docs`

### Step 0.2: Core Models and CRUD
- Entities: SourceAccount, Playlist, Track, TrackIdentity, PlaylistTrack, SearchCandidate, Download, LibraryFile, OAuthToken, OAuthState
- CRUD endpoints for sources, playlists, and tracks
- Pydantic schemas for request/response shapes

**Validation Criteria:**
1. Create/list/update/delete operations succeed for sources/playlists/tracks
2. Foreign key constraints respected for relationships
3. Unit tests pass for CRUD operations

### Step 0.3: OAuth and Secret Management Foundation
- SECRET_KEY used to encrypt refresh tokens at rest
- Generic OAuth token storage endpoints
- Spotify OAuth (PKCE) endpoints: authorize, callback, refresh
- Environment variables loaded from `backend/.env` (or process env)

**Validation Criteria:**
1. Missing Spotify env vars cause a clear 5xx only when Spotify endpoints are invoked
2. Successful OAuth flow stores encrypted refresh token
3. Token refresh updates access token and expiry in DB

### Step 0.4: Frontend Dev and Build Integration
- Vite dev server proxies `/api` to backend
- Frontend uses relative API paths
- Production build outputs to `backend/app/static`

**Validation Criteria:**
1. Dev mode: calls to `/api/v1/health` succeed via proxy
2. Build mode: SPA loads from backend and can reach API

### Step 0.5: Test Suite Baseline
- Pytest with pytest-asyncio
- Shared in-memory SQLite for tests; app startup/shutdown fixture
- Tests for health, CRUD, crypto, mocked Spotify OAuth

**Validation Criteria:**
1. `pytest -q` passes locally
2. OAuth tests mock external HTTP calls reliably

## Phase 1 — Normalization and Identity/Candidate APIs

### Step 1.1: Track Normalization Utilities
- Normalize artist/title (remove featured markers, version notes, punctuation)
- Extract features (primary artist, clean title, remix/live flags)
- Duration tolerance helpers for matching
- UI: Normalization playground page to paste artist/title and preview normalized outputs in real time
- UI: Inline normalization preview in track create/edit form

Implementation notes:
- Backend utilities added under `backend/app/utils/normalize.py`.
- Public preview endpoint: `GET /api/v1/tracks/normalize/preview?artists=...&title=...`.
- Frontend demo playground lives on the home page below the health check.

**Validation Criteria:**
1. Unit tests cover common patterns and edge cases (feat., remaster, live)
2. Normalized output is deterministic for same inputs
 3. In the playground, typing updates normalized fields instantly without page refresh
 4. Track form shows a preview of normalized fields before save (basic demo provided; full form wiring in later steps)

### Step 1.2: TrackIdentity Endpoints
- CRUD endpoints for identities
- List with filters (by track_id, fingerprint presence, created range)
- Link identities to tracks upon creation/update
- UI: Identities list view and detail panel linked from track detail
- UI: Form to edit identity fields and save changes

Implementation notes:
- Model extended with `fingerprint`, `created_at`, `updated_at`.
- Endpoint base: `/api/v1/identities` supporting list filters: `track_id`, `has_fingerprint`, `created_from`, `created_to`.
- Tracks auto-generate a manual identity on creation (`manual:{id}`).
- Frontend basic panel (temporary) added to home for listing & editing identities.

**Validation Criteria:**
1. Identities can be created, listed, updated, and deleted
2. Creating/Updating a track generates or updates an identity record
3. From the track detail, user can open an identity tab, edit, and save
4. Identity list supports filtering by track and date

### Step 1.3: SearchCandidate Endpoints
- CRUD for candidates linked to a track
- Fields for provider, url, title, channel, duration, score
- Basic list sorting by score and duration delta
- UI: Candidates table on track detail with sortable columns and actions (attach/detach, set as preferred)
- UI: Manual add dialog to add a candidate by URL and metadata

Implementation notes:
- Endpoint base `/api/v1/candidates` with query params: `track_id`, `sort=score|duration_delta`, `chosen_only`.
- Computed field `duration_delta_sec` returned when track duration known.
- Choosing a candidate: `POST /api/v1/candidates/{id}/choose` sets chosen and unsets others for the track.
- Frontend temporary panel added on home page for selection, viewing, sorting, choosing, and manual add.

**Validation Criteria:**
1. Candidates attach to a track and can be ranked
2. API returns candidates sorted as requested
3. Sorting by score/duration updates the visible order in the table
4. Manual add by URL creates a candidate visible immediately

### Step 1.4: JSON Import (Manual Source)
- Endpoint/UI to upload JSON describing tracks
- Create tracks + identities from uploaded data
- UI: Drag-and-drop import page with schema hint and preview table
- UI: Dry-run mode showing what will be created/updated before confirming

JSON Schema (English field names):

Required fields per object:
- artists (string)
- title (string)
- genre (string, non-empty)
- bpm (integer > 0)

Optional:
- duration (string mm:ss) -> converted to duration_ms if provided

Example:
[
	{"artists": "Sabrina Carpenter", "title": "Espresso", "genre": "Pop", "bpm": 120, "duration": "2:56"}
]

Duplicate detection uses the normalized (artists, title) pair; duplicates are skipped on actual import.
Dry-run returns an items array with duplicate flag and counts.

Implemented UI:
- Added an Import tab (no client-side router dependency) with drag-and-drop JSON zone.
- Provides Dry Run button (preview table with duplicate highlighting + errors list) and Confirm Import.
- Minimal styling; future enhancements (pagination, inline editing) can be layered without breaking API.

**Validation Criteria:**
1. Sample JSON imports successfully and creates records
2. Duplicate imports do not create duplicate tracks
3. Dry-run preview matches the subsequent import result
4. Import shows success/failure toasts with counts

## Phase 2 — YouTube Search and Download

### Step 2.1: YouTube Search Scoring and Extended/Club Mix Preference
- Implement YouTube search scoring for track queries (details to be defined at development start)
- Support preference for Extended/Club Mix results (details to be defined)
- Persist top candidates and their scores for later selection (details to be defined)
- Provide frontend UI to trigger search, view candidates, and select a preferred one (details to be defined)
- Default search provider: yt-dlp `ytsearch` (no API key required)

Implementation (completed):
- Added `utils.youtube_search` with deterministic scoring: token overlap + duration proximity + optional extended mix bonus.
- Endpoint: `GET /api/v1/tracks/{track_id}/youtube/search?prefer_extended=&persist=&limit=`.
- Persistence creates `SearchCandidate` rows (deduplicated by external_id) when `persist=true`.
- Fake mode via `YOUTUBE_SEARCH_FAKE=1` supplies deterministic sample results for tests.
- Frontend `YouTubeSearchPanel` allows selecting track, toggling extended mix preference, choosing persistence, and viewing results.

**Validation Criteria:**
1. API returns scored YouTube candidates for a given track
2. UI exposes a toggle to prefer Extended/Club Mix
3. User can select and persist a candidate for a track
4. End-to-end flow executes without runtime errors

### Step 2.2: Download Queue and Worker (Implemented)
- In-process asyncio queue/worker with configurable concurrency
- Job lifecycle: queued → running → done/failed with timestamps
- UI: Downloads page that lists downloads and updates via polling

APIs:
- POST `/api/v1/downloads/enqueue?track_id={id}&candidate_id={optional}&provider=yt_dlp`
- GET `/api/v1/downloads/?status=&track_id=&limit=&offset=`
- GET `/api/v1/downloads/{id}`

Worker behavior:
- On startup, a worker is started unless `DISABLE_DOWNLOAD_WORKER=1` (used in tests)
- Each job sets status running, simulates work, then marks done/failed and commits
- On shutdown, the worker is stopped cleanly

Test helpers (not in OpenAPI):
- POST `/api/v1/downloads/_restart_worker` body `{ concurrency, simulate_seconds }` — starts a worker in the app context
- POST `/api/v1/downloads/_wait_idle` body `{ timeout, track_id?, stop_after? }` — waits for queue to drain and optionally stops the worker

Notes:
- SQLite for tests uses a shared in-memory configuration so the worker and API share the same DB
- Tests disable worker auto-start via `DISABLE_DOWNLOAD_WORKER=1` and control it via helper endpoints to avoid asyncio warnings

**Validation Criteria:**
1. Enqueuing multiple jobs processes them concurrently up to a limit
2. Job states persist and are queryable via API
3. Downloads page refreshes to reflect status transitions without full reload

 

### Step 2.3: yt-dlp Integration and Tagging
- Download best candidate audio (m4a/mp3) via yt-dlp
- ffmpeg post-processing and ID3/metadata writing
- File naming convention and output directory settings
- UI: Progress indicator on per-download row; link to open file location

Implementation (in progress):
- Added `utils.downloader.perform_download` supporting Fake mode via `DOWNLOAD_FAKE=1` and real yt-dlp path via `YT_DLP_BIN`/`FFMPEG_BIN`.
- Worker now performs actual downloads when `simulate_seconds=0` in `_restart_worker` or on startup.
- Output directory configurable via `LIBRARY_DIR` (default `library/` at project root). Files are named `Artists - Title.ext` with de-dup suffix.
- Checksums (SHA-256) and file size recorded on `Download` row.
- Minimal test `test_download_yt_dlp_fake.py` validates fake mode end-to-end without external tools.
 - Tag policy: we always drop source tags (`-map_metadata -1`) and write tags from our Track (artist, title, album, genre, bpm). MP3 uses ID3v2.3 with ID3v1 compatibility. Source metadata via yt‑dlp `--add-metadata` is disabled by default.
 - Cover policy: we embed a thumbnail only when the track has no preferred cover. When Spotify integration is available, its album image will take priority; YouTube thumbnail is used as a fallback.

Tagging is stubbed for now; ID3/metadata writing will be completed alongside Step 2.4.

**Validation Criteria:**
1. Downloaded file exists with expected filename and format
2. Tags include artist, title, album (if provided), cover when available
3. Progress column updates from queued→running→completed/failed in the UI

### Step 2.4: Download API and Library Tracking
- Endpoints: enqueue, status, list, cancel (if feasible)
- Update Download and LibraryFile records upon completion
- UI: Button on track/candidate to enqueue; library table shows completed items

Implementation (completed):
- Added library endpoints: `GET /api/v1/library/files` and `GET /api/v1/library/files/{id}` with optional `track_id` filter.
- Worker writes/updates `LibraryFile` upon successful completion with size, mtime, checksum.
- Added cancel endpoint `POST /api/v1/downloads/cancel/{id}` for queued jobs (409 if running).
- README and API docs updated accordingly; tests cover library creation and listing and cancel behavior.

**Validation Criteria:**
1. API returns a download id; status reflects progress and final result
2. LibraryFile links to the corresponding track and file path
3. Enqueue from UI creates a new row in queue immediately

### Step 2.5: In‑App Audio Player (Stream + Seek)
- Backend: Stream endpoint to serve audio with HTTP Range support (206 Partial Content)
	- `GET /api/v1/library/files/{id}/stream` reads from the library storage
	- Sets `Accept-Ranges: bytes`, `Content-Range`, correct `Content-Type` (audio/mpeg, audio/mp4)
	- Provides ETag/Cache-Control for efficient playback
- Frontend: Player UI using HTML5 `<audio>` (or waveform component)
	- Now Playing bar with play/pause, seek slider, elapsed/remaining time, volume
	- Play from LibraryFile entries; keyboard shortcuts optional
- Integration: Dev proxy forwards headers; backend serves Range correctly.

Implementation (completed):
- Added `/api/v1/library/files/{id}/stream` with single-range support, ETag/Last-Modified/Cache-Control, and proper MIME.
- Frontend Downloads page now lists Library files with a Play button and a fixed Now Playing bar using the stream endpoint.
- Tests cover full (200) and partial (206) responses and headers.

**Validation Criteria:**
1. Stream endpoint supports Range and seeking without full re-download
2. Player can play, pause, seek, and adjust volume reliably
3. Selecting a LibraryFile starts playback within 2 seconds on local network
4. Scrubbing updates current time accurately and resumes audio promptly

## Phase 3 — Spotify Ingestion (Playlists)

### Step 3.1: Playlist Discovery
- List user playlists via Spotify API (requires env vars)
- Select playlists to sync and persist selection

**Validation Criteria:**
1. API returns playlists with names and ids
2. Selection persists between sessions
 
Implementation (completed):
- Added `selected` flag to `Playlist` model and auto-migration.
- Endpoint: `GET /api/v1/playlists/spotify/discover?account_id={id}&persist=true|false` to fetch user playlists using the stored OAuth token.
- Endpoint: `POST /api/v1/playlists/spotify/select` body `{ account_id, playlist_ids: string[] }` marks selected playlists (others for the account are unselected).
- Enhanced `GET /api/v1/playlists/` filters: `provider`, `account_id`, `selected`.
- Frontend: new Playlists page to discover from Spotify and toggle selection, wired in the navbar. On load, it attempts a silent token refresh (if a refresh token is stored) and shows a "Connected to Spotify" indicator, hiding the Connect button when already connected.
- Tests: Added `test_spotify_playlists.py` mocking Spotify API to validate discover and selection persistence.

### Step 3.2: Playlist Sync Job
- Fetch items for selected playlists
- Create/Update Tracks and PlaylistTrack mappings
- Generate/Update identities for new/changed tracks

**Validation Criteria:**
1. First sync creates tracks and mappings with no duplicates
2. Re-running sync is idempotent

Implementation (completed):
- Endpoint: `POST /api/v1/playlists/spotify/sync?account_id={id}` optionally with body `{ "playlist_ids": ["..." ] }`.
- For each playlist item: upserts `Track` (with normalization), creates `TrackIdentity` for Spotify id if missing, and creates `PlaylistTrack` link once.
- Uses album images for `cover_url` when available and fills `isrc` if present. `added_at` is parsed to a datetime. Repeated runs do not duplicate tracks or links.

### Step 3.3: Incremental Sync
- Track cursors/ETags to fetch only changes
- Handle additions/removals and track metadata updates

**Validation Criteria:**
1. Subsequent syncs process only new/changed items
2. Deleted items are reflected in mappings

### Step 3.4: UI for Spotify Connection and Sync
- Connect account, choose playlists, show sync progress

**Validation Criteria:**
1. User can select playlists and trigger sync from UI
2. Progress and outcomes are visible in real time or via refresh

## Phase 4 — Matching and Deduplication

### Step 4.1: Candidate Scoring Heuristics
- Fuzzy match on title/artist, channel reputation, duration delta, keywords (official/lyrics/live)

**Validation Criteria:**
1. Scoring model ranks official or best-fit results higher in benchmarks
2. Thresholds reduce false positives in tests

### Step 4.2: Duplicate Prevention
- Check existing LibraryFile and prior successful downloads before enqueueing

**Validation Criteria:**
1. Re-enqueueing same track does not redownload identical file
2. API returns informative status for duplicate attempts

### Step 4.3: Manual Override
- UI/API to override best candidate and force selection

**Validation Criteria:**
1. User can pick an alternate candidate and download succeeds
2. Selection is stored for future reference

## Phase 5 — Dockerization and Synology Deployment

### Step 5.1: Dockerfile and Multi-Stage Build
- Multi-stage Dockerfile for backend (and optional frontend builder)
- Smaller runtime image with only needed binaries (ffmpeg, yt-dlp)

**Validation Criteria:**
1. Image builds locally for amd64 (and arm64 if targeted)
2. Container starts and serves API and SPA

### Step 5.2: docker-compose and Volumes
- Compose example with volumes for library (`/music`) and config (`/config`)
- Environment variables for SECRET_KEY, Spotify, TZ, PUID/PGID

**Validation Criteria:**
1. Downloads persist under mapped `/music`
2. DB/.env/logs persist under `/config`

### Step 5.3: Healthcheck and Logging
- Container healthcheck endpoint
- Structured logs to stdout/stderr suitable for Synology log viewer

**Validation Criteria:**
1. `docker ps` shows healthy status after startup
2. Logs contain request traces and download events without secrets

### Step 5.4: Synology Deployment Guide
- Document DSM steps, permissions, and bind mounts

**Validation Criteria:**
1. App deploys on Synology and writes to shared folders with correct ownership
2. Restart preserves configuration and library

## Phase 6 — Settings and Admin UX

### Step 6.1: Settings Backend
- Persist settings in DB (env as defaults) for library path, quality, concurrency

**Validation Criteria:**
1. Settings API reads/writes values and validates ranges
2. Changes apply without rebuild/redeploy

### Step 6.2: Settings Frontend
- UI for changing settings with form validation and feedback

**Validation Criteria:**
1. Admin can update settings from UI and see confirmation
2. Invalid inputs are rejected with clear messages

### Step 6.3: Jobs and Logs Views
- Pages to view download queue, history, and recent logs

**Validation Criteria:**
1. Queue and history tables render with pagination
2. Logs display recent events with filtering

### Step 6.4: Config Export/Import
- Export/import non-secret configuration as JSON

**Validation Criteria:**
1. Export produces valid JSON excluding secrets
2. Import applies values and validates types

## Phase 7 — Reliability, Observability, and CI

### Step 7.1: CI Pipeline
- Lint, type-check, tests, and container build on main PRs

**Validation Criteria:**
1. Pipeline runs automatically and blocks on failures
2. Artifacts (image) produced on tagged releases

### Step 7.2: Logging and Metrics
- Request IDs, structured logs, minimal metrics endpoint

**Validation Criteria:**
1. Each request includes a traceable correlation id
2. Metrics endpoint exposes basic counters (requests, downloads)

### Step 7.3: Retry and Backoff
- Standardized retry/backoff for provider calls and downloads

**Validation Criteria:**
1. Transient failures are retried within limits
2. Backoff behavior observable in logs

## Phase 8 — Additional Providers (Stretch)

### Step 8.1: JSON/CSV Import Enhancements
- Robust mapping, schema validation, and preview before import

**Validation Criteria:**
1. Invalid rows flagged with actionable errors
2. Preview allows selective import

### Step 8.2: SoundCloud Provider
- OAuth/ingestion and candidate generation for SoundCloud

**Validation Criteria:**
1. Playlists/tracks can be ingested from a connected account
2. Candidates generated and downloadable via existing pipeline

### Step 8.3: Additional Provider (e.g., Bandcamp or local folders)
- Minimal viable ingestion path for one more source

**Validation Criteria:**
1. Source integrated end-to-end (ingest → match → download)
2. Tests cover critical flows
