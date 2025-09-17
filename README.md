# Music Downloader (FastAPI + React)

Simple monorepo with:
- `backend/` — FastAPI application (CORS enabled), async SQLAlchemy with SQLite, `/api/v1/health` endpoint, OAuth helpers.
- `frontend/` — React + Vite app that checks API health and uses a dev proxy to the backend.

## Run locally (Windows cmd.exe)

### Backend

1) Create a virtual environment and install dependencies
```
cd d:\Dev\Projects\music_downloader
py -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

2) Configure environment variables (optional)
- Copy `backend/.env.example` to `backend/.env` and adjust values.
- You can also set variables in your shell or IDE.

3) Start the API server (pick one)
```
# Option A: explicit app path
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# Option B: helper script (ensures sys.path and reload dirs)
python run_api.py
```

API root: http://localhost:8000/
Health:   http://localhost:8000/api/v1/health
Info:     http://localhost:8000/api/v1/info

### Frontend
```
cd d:\Dev\Projects\music_downloader\frontend
npm install
npm run dev
```

Vite dev server: http://localhost:5173

Notes:
- The Vite dev server proxies requests starting with `/api` to `http://localhost:8000` (configured in `frontend/vite.config.ts`).
- The frontend uses relative URLs (e.g., `/api/v1/health`) during development, so no CORS tweaks are needed.

Production build:
- Run `npm run build` in `frontend/` to emit assets into `backend/app/static`.
- The `backend/app/static` folder is ignored by Git (except for a `.gitkeep` placeholder). Build artifacts are not committed.

Frontend navigation (React Router):
- `/` Dashboard
- `/tracks` Tracks list
- `/tracks/:id` Track detail with tabs: `overview`, `identities`, `candidates`, `search`
- `/playlists` Discover and select Spotify playlists
- `/import` JSON import workflow
- `/tools` Normalization playground

## Environment variables
Variables are loaded from `backend/.env` (via python-dotenv) and can be overridden by your shell or IDE run configuration.

- `SECRET_KEY` (recommended): 32+ char string used to encrypt secrets (e.g., OAuth refresh tokens).
- `DATABASE_URL` (optional): SQLAlchemy URL. Default is `sqlite+aiosqlite:///./music.db`.
- Spotify OAuth (optional, for the Spotify endpoints):
	- `SPOTIFY_CLIENT_ID`
	- `SPOTIFY_CLIENT_SECRET`
	- `SPOTIFY_REDIRECT_URI` (e.g., `http://localhost:8000/api/v1/oauth/spotify/callback` or a frontend URL that forwards to the backend callback)

For playlist discovery (Step 3.1):
- Create a Spotify `SourceAccount` via `/api/v1/sources/accounts` (e.g., name "My Spotify").
- Complete the OAuth flow or POST an `OAuthToken` with a valid access token.
- Use the Playlists page to Discover (optionally persist) and Select playlists for sync.

Frontend UX:
- The Playlists page tries a silent token refresh on load; if successful it shows "Connected to Spotify" and immediately discovers playlists.
- If not connected yet, click "Connect to Spotify" to initiate OAuth; after consent you'll be redirected back to `/playlists`.

- YouTube Search:
	- `YOUTUBE_SEARCH_LIMIT` (default 8) maximum results to request.
	- `YOUTUBE_SEARCH_FAKE=1` return deterministic fake results (used in tests).

Install `yt-dlp` locally (e.g., `pip install yt-dlp`) for real searches; it's not yet pinned in `backend/requirements.txt` until download steps.

## Testing

From the `backend/` folder (or project root with the venv activated):
```
pytest -q
```

The test suite uses a shared in-memory SQLite database and runs FastAPI startup/shutdown once per session to auto-create tables.

## In‑App Audio Player

- Stream endpoint: `GET /api/v1/library/files/{id}/stream` with HTTP Range (206), ETag/Last-Modified, and correct audio MIME.
- Frontend Downloads page shows a Play button per LibraryFile and a fixed Now Playing audio bar with native seek/volume.

If you test locally on Windows cmd.exe, ensure you activate the project virtual environment at the repo root:
```
d:\Dev\Projects\music_downloader\.venv\Scripts\activate
```

## Project structure (excerpt)
```
backend/
	app/
		api/v1/        # Routers: health, sources, playlists, tracks, oauth, oauth_spotify
		db/            # Async SQLAlchemy engine/session and models
		schemas/       # Pydantic DTOs
		utils/         # Crypto helper (Fernet-like with SECRET_KEY)
		main.py        # FastAPI app entrypoint
frontend/
	src/             # React app (Vite)
old/               # Legacy code kept for reference
```

## Current capabilities
- FastAPI backend with async SQLite (aiosqlite) and auto table creation at startup.
- Domain models: sources, playlists, tracks, identities, candidates, downloads, library files, OAuth tokens.
- CRUD endpoints for sources, playlists, and tracks.
- OAuth storage API and Spotify OAuth (PKCE) endpoints (authorize, callback, refresh) with encrypted refresh tokens.
- React + Vite frontend with panels: normalization playground, identities, YouTube search (scored), candidates list, JSON import.
	The tracks list shows cover images, genre, bpm, duration, and timestamps.
- Playlist integration:
	- Discover & select Spotify playlists, sync tracks (creates/updates Tracks & PlaylistTrack mappings)
	- Track Manager playlist dropdown filters to the selected playlist using `/api/v1/playlists/{id}/entries` preserving ordering.
	- Playlist memberships column shows all playlists (with position) a track belongs to.
<!-- Removed: Spotify audio features ingestion (fields deprecated and removed from the schema) -->
- Increased `/api/v1/tracks` max `limit` query parameter to 1000 for broader library browsing.
- Pytest test suite (health, CRUD basics, crypto, mocked Spotify OAuth, YouTube search scoring with fake results).
- YouTube search endpoint: `GET /api/v1/tracks/{track_id}/youtube/search` params:
	- `prefer_extended` (bool) boosts Extended/Club Mix results.
	- `persist` (bool, default true) persists top scored results as candidates.
	- `limit` (optional int) overrides search limit.
	Scoring blends text token overlap, duration proximity, extended mix bonus, and small penalties for missing tokens.
- Single-source name/version (`backend/app/app_meta.py`) exposed via `/api/v1/info`.

### Cover images
- When running YouTube search with `persist=true` for a track that has no cover yet, the top candidate's YouTube thumbnail is used.
- Choosing a YouTube candidate also fills the track cover if it is missing.
- You can refresh a cover via `POST /api/v1/tracks/{id}/cover/refresh`:
  - If a Spotify identity exists and a valid token is configured, the track's album art is used.
  - Otherwise, if a chosen YouTube candidate exists, its thumbnail is used.

### Downloads
- Endpoints:
	- `POST /api/v1/downloads/enqueue?track_id={id}&candidate_id={optional}&provider=yt_dlp`
	- `GET /api/v1/downloads/?status=&track_id=&limit=&offset=`
	- `GET /api/v1/downloads/{id}`
	- `POST /api/v1/downloads/cancel/{id}` (cancel queued; returns 409 if already running)
	- `GET /api/v1/library/files` and `GET /api/v1/library/files/{id}` (library tracking)
- Worker:
	- Starts on app startup by default; set `DISABLE_DOWNLOAD_WORKER=1` to disable (used in tests)
	- Updates status from queued → running → done/failed with timestamps
	- Real downloads when `simulate_seconds=0` or in normal startup; set `DOWNLOAD_FAKE=1` to create a small placeholder file without yt-dlp/ffmpeg.
	- Configure binaries and output:
		- `LIBRARY_DIR` (default `./library`) to store downloaded files
		- `YT_DLP_BIN` and `FFMPEG_BIN` if not on PATH
		- `PREFERRED_AUDIO_FORMAT` (default `mp3`)
- Testing:
	- Test-only helpers (not shown in OpenAPI):
		- `POST /api/v1/downloads/_restart_worker` with `{ "concurrency": 2, "simulate_seconds": 0.05 }`
		- `POST /api/v1/downloads/_wait_idle` with `{ "timeout": 3.0, "track_id": <id>, "stop_after": true }`
	- These helpers make tests deterministic and ensure clean shutdown without asyncio warnings

## Next steps
- Track normalization utilities applied server-side when creating tracks.
- Endpoints for identities, candidates, and downloads; scoring and best-candidate selection.
- Providers: Spotify ingestion (playlists/tracks), YouTube search/downloader with duplicate avoidance.
- Background worker/queue for downloads, and integration with tools like yt-dlp/ffmpeg.
- Frontend pages for source linking, playlist browsing, search, and downloads management.
- CI pipeline and optional DB migrations.

## Changelog
See `CHANGELOG.md` for release notes and version history.
