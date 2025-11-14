from fastapi import FastAPI
import logging
import os
import subprocess
import shutil
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from typing import List, Dict, Any
from logging.config import dictConfig

# Apply logging configuration as early as possible (module import time)
try:
    from .core.logging_config import get_uvicorn_log_config  # type: ignore
    _lvl_name = os.environ.get("APP_LOG_LEVEL", "INFO").upper()
    _lvl = getattr(logging, _lvl_name, logging.INFO)
    dictConfig(get_uvicorn_log_config(_lvl))
except Exception:
    # Fallback to a simple timestamped format
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

# Support both execution modes:
# - "uvicorn backend.app.main:app" (package-relative imports)
# - "uvicorn main:app" with sys.path pointing to backend/app (flat imports)
try:
    from .api.v1.health import router as health_router  # type: ignore
    from .api.v1.sources import router as sources_router  # type: ignore
    from .api.v1.playlists import router as playlists_router  # type: ignore
    from .api.v1.tracks import router as tracks_router  # type: ignore
    from .api.v1.tracks_import import router as tracks_import_router  # type: ignore
    from .api.v1.identities import router as identities_router  # type: ignore
    from .api.v1.candidates import router as candidates_router  # type: ignore
    from .api.v1.playlist_tracks import router as playlist_tracks_router  # type: ignore
    from .api.v1.oauth import router as oauth_router  # type: ignore
    from .api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from .db.session import engine, Base  # type: ignore
    from .core.config import settings  # type: ignore
    from .api.v1.downloads import router as downloads_router  # type: ignore
    from .api.v1.library import router as library_router, stream_router  # type: ignore
    from .worker.downloads_worker import download_queue, DownloadQueue  # type: ignore
except Exception:  # pragma: no cover
    from api.v1.health import router as health_router  # type: ignore
    from api.v1.sources import router as sources_router  # type: ignore
    from api.v1.playlists import router as playlists_router  # type: ignore
    from api.v1.tracks import router as tracks_router  # type: ignore
    from api.v1.tracks_import import router as tracks_import_router  # type: ignore
    from api.v1.identities import router as identities_router  # type: ignore
    from api.v1.candidates import router as candidates_router  # type: ignore
    from api.v1.playlist_tracks import router as playlist_tracks_router  # type: ignore
    from api.v1.oauth import router as oauth_router  # type: ignore
    from api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from db.session import engine, Base  # type: ignore
    from core.config import settings  # type: ignore
    from api.v1.downloads import router as downloads_router  # type: ignore
    from api.v1.library import router as library_router, stream_router  # type: ignore
    from worker.downloads_worker import download_queue, DownloadQueue  # type: ignore

tags_metadata = [
    {"name": "health", "description": "Health checks and basic service info."},
    {"name": "sources", "description": "Manage source accounts (Spotify, SoundCloud, Manual)."},
    {"name": "playlists", "description": "Manage playlists from providers and local metadata."},
    {"name": "tracks", "description": "Manage track catalog and normalized metadata."},
    {"name": "oauth", "description": "OAuth token storage and provider-specific flows."},
]

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "API for ingesting music from external providers (e.g., Spotify),"
        " searching/downloading candidates (e.g., YouTube), and managing a local library."
    ),
    openapi_tags=tags_metadata,
    # Serve docs under /api/* to match API prefix
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    contact={"name": settings.app_name},
    license_info={
        "name": "MIT",
    },
)

# CORS: allow Vite frontend during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    # Ensure a logging configuration with timestamps exists so module and uvicorn logs are visible
    try:
        level_name = os.environ.get("APP_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        try:
            # Prefer our centralized dictConfig if available
            from .core.logging_config import get_uvicorn_log_config  # type: ignore
        except Exception:
            get_uvicorn_log_config = None  # type: ignore

        if get_uvicorn_log_config:
            dictConfig(get_uvicorn_log_config(level))
        else:
            # Fallback to basicConfig with time
            logging.basicConfig(level=level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
            logging.getLogger("uvicorn").setLevel(level)
            logging.getLogger("uvicorn.error").setLevel(level)
            logging.getLogger("uvicorn.access").setLevel(level)
        # Ensure our app loggers are at the configured level
        logging.getLogger("backend").setLevel(level)
        logging.getLogger("backend.app").setLevel(level)
    except Exception:
        pass
    # Create tables (simple init, replace by migrations later)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight auto-migrations for legacy SQLite DBs (best-effort, replace with Alembic later)
        try:  # pragma: no cover
            result = await conn.exec_driver_sql("PRAGMA table_info(track_identities)")
            cols = [row[1] for row in result.fetchall()]
            alter_statements = []
            if "fingerprint" not in cols:
                alter_statements.append("ALTER TABLE track_identities ADD COLUMN fingerprint VARCHAR(500)")
            if "created_at" not in cols:
                alter_statements.append("ALTER TABLE track_identities ADD COLUMN created_at DATETIME")
            if "updated_at" not in cols:
                alter_statements.append("ALTER TABLE track_identities ADD COLUMN updated_at DATETIME")
            for stmt in alter_statements:
                try:
                    await conn.exec_driver_sql(stmt)
                except Exception:
                    pass
        except Exception:
            pass

        # Migration for tracks table
        try:  # pragma: no cover
            result = await conn.exec_driver_sql("PRAGMA table_info(tracks)")
            cols = [row[1] for row in result.fetchall()]
            alter_statements = []
            if "release_date" not in cols:
                alter_statements.append("ALTER TABLE tracks ADD COLUMN release_date DATETIME")
            if "spotify_added_at" not in cols:
                alter_statements.append("ALTER TABLE tracks ADD COLUMN spotify_added_at DATETIME")
            for stmt in alter_statements:
                try:
                    await conn.exec_driver_sql(stmt)
                except Exception:
                    pass
        except Exception:
            pass

        # Auto-migrate new Track columns (genre, bpm) if missing (Step 1.4)
        try:  # pragma: no cover
            result = await conn.exec_driver_sql("PRAGMA table_info(tracks)")
            tcols = [row[1] for row in result.fetchall()]
            if "genre" not in tcols:
                try:
                    await conn.exec_driver_sql("ALTER TABLE tracks ADD COLUMN genre VARCHAR(200)")
                except Exception:
                    pass
            if "bpm" not in tcols:
                try:
                    await conn.exec_driver_sql("ALTER TABLE tracks ADD COLUMN bpm INTEGER")
                except Exception:
                    pass
        except Exception:
            pass

        # Repair legacy SQLite schemas where tracks.id is NOT a PRIMARY KEY (causes NOT NULL constraint on insert)
        # We rebuild the table with the correct schema and preserve data.
        try:  # pragma: no cover
            result = await conn.exec_driver_sql("PRAGMA table_info(tracks)")
            rows = result.fetchall()
            if rows:
                # rows: cid, name, type, notnull, dflt_value, pk
                id_row = next((r for r in rows if r[1] == "id"), None)
                if id_row is not None:
                    id_pk_flag = id_row[5]
                    if not id_pk_flag:
                        print("[startup] Migrating tracks table to set id as PRIMARY KEY AUTOINCREMENT …")
                        # Disable FKs for table rebuild
                        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
                        # Create new table with correct schema
                        await conn.exec_driver_sql(
                            """
                            CREATE TABLE IF NOT EXISTS tracks_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                title VARCHAR(500) NOT NULL,
                                artists VARCHAR(500) NOT NULL,
                                album VARCHAR(500),
                                duration_ms INTEGER,
                                isrc VARCHAR(50),
                                year INTEGER,
                                explicit BOOLEAN NOT NULL DEFAULT 0,
                                cover_url VARCHAR(1000),
                                normalized_title VARCHAR(500),
                                normalized_artists VARCHAR(500),
                                genre VARCHAR(200),
                                bpm INTEGER,
                                release_date DATETIME,
                                spotify_added_at DATETIME,
                                created_at DATETIME,
                                updated_at DATETIME
                            )
                            """
                        )
                        # Determine columns present to copy
                        existing_cols = [r[1] for r in rows]
                        desired = [
                            "id","title","artists","album","duration_ms","isrc","year","explicit","cover_url",
                            "normalized_title","normalized_artists","genre","bpm","release_date","spotify_added_at","created_at","updated_at"
                        ]
                        copy_cols = [c for c in desired if c in existing_cols]
                        cols_csv = ",".join(copy_cols)
                        await conn.exec_driver_sql(
                            f"INSERT INTO tracks_new ({cols_csv}) SELECT {cols_csv} FROM tracks"
                        )
                        await conn.exec_driver_sql("DROP TABLE tracks")
                        await conn.exec_driver_sql("ALTER TABLE tracks_new RENAME TO tracks")
                        # Recreate indexes
                        await conn.exec_driver_sql(
                            "CREATE INDEX IF NOT EXISTS ix_tracks_normalized_title ON tracks (normalized_title)"
                        )
                        await conn.exec_driver_sql(
                            "CREATE INDEX IF NOT EXISTS ix_tracks_normalized_artists ON tracks (normalized_artists)"
                        )
                        await conn.exec_driver_sql(
                            "CREATE INDEX IF NOT EXISTS ix_track_isrc ON tracks (isrc)"
                        )
                        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
                        print("[startup] Tracks table migration complete.")
        except Exception as _e:
            # Best-effort; continue startup if migration isn't applicable
            try:
                print(f"[startup] Tracks table migration skipped or failed: {_e}")
            except Exception:
                pass

        # Auto-migrate playlists.selected column (Step 3.1)
        try:  # pragma: no cover
            result = await conn.exec_driver_sql("PRAGMA table_info(playlists)")
            pcols = [row[1] for row in result.fetchall()]
            if "selected" not in pcols:
                try:
                    await conn.exec_driver_sql("ALTER TABLE playlists ADD COLUMN selected BOOLEAN DEFAULT 0 NOT NULL")
                except Exception:
                    pass
        except Exception:
            pass

        # Auto-migrate library_files.actual_duration_ms column
        try:  # pragma: no cover
            result = await conn.exec_driver_sql("PRAGMA table_info(library_files)")
            lfcols = [row[1] for row in result.fetchall()]
            if "actual_duration_ms" not in lfcols:
                try:
                    await conn.exec_driver_sql("ALTER TABLE library_files ADD COLUMN actual_duration_ms INTEGER")
                except Exception:
                    pass
        except Exception:
            pass

        # (Removed: audio feature columns auto-migration no longer needed)

    # Start download worker(s) unless disabled (e.g., in tests)
    if os.environ.get("DISABLE_DOWNLOAD_WORKER", "0") not in {"1", "true", "TRUE", "True"}:
        # Allow configuring concurrency and simulation via env; default to real downloads (simulate_seconds=0)
        from .worker import downloads_worker as dw  # lazy import to set global
        try:
            conc = int(os.environ.get("DOWNLOAD_CONCURRENCY", "2"))
        except Exception:
            conc = 2
        try:
            sim_seconds = float(os.environ.get("DOWNLOAD_SIMULATE_SECONDS", "0"))
        except Exception:
            sim_seconds = 0.0
        dw.download_queue = DownloadQueue(concurrency=conc, simulate_seconds=sim_seconds)
        print(f"[startup] Download worker started concurrency={conc} simulate_seconds={sim_seconds}")
        await dw.download_queue.start()

    # Log effective library directory
    try:
        from .core.config import settings as _settings  # type: ignore
        print(f"[startup] LIBRARY_DIR={_settings.library_dir}")
    except Exception:
        pass

    # Log yt-dlp version for diagnostics
    try:  # pragma: no cover
        yt = os.environ.get("YT_DLP_BIN") or shutil.which("yt-dlp")
        if yt:
            ver = subprocess.check_output([yt, "--version"], text=True, timeout=5).strip()
            logging.getLogger("backend.app").info(f"yt-dlp version={ver} bin={yt}")
    except Exception:
        pass

    # Enqueue any downloads that are already queued at startup
    try:  # pragma: no cover
        from sqlalchemy import select
        from .db.models.models import Download, DownloadStatus  # type: ignore
        from .db.session import async_session  # type: ignore
        async with async_session() as session:
            result = await session.execute(select(Download).where(Download.status == DownloadStatus.queued))
            for dl in result.scalars().all():
                if dw.download_queue:
                    await dw.download_queue.enqueue(dl.id)
    except Exception:
        pass

@app.on_event("shutdown")
async def on_shutdown():
    from .worker import downloads_worker as dw
    try:
        dq = dw.download_queue
        if dq:
            await dq.stop()
    except Exception:
        # Ignore shutdown errors (e.g., event loop closed in test teardown)
        pass
    finally:
        dw.download_queue = None

# Routes
app.include_router(health_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")
app.include_router(playlists_router, prefix="/api/v1")
app.include_router(tracks_router, prefix="/api/v1")
app.include_router(tracks_import_router, prefix="/api/v1")
app.include_router(identities_router, prefix="/api/v1")
app.include_router(candidates_router, prefix="/api/v1")
app.include_router(playlist_tracks_router, prefix="/api/v1")
app.include_router(oauth_router, prefix="/api/v1")
app.include_router(oauth_spotify_router, prefix="/api/v1")
app.include_router(downloads_router, prefix="/api/v1")
app.include_router(library_router, prefix="/api/v1")
app.include_router(stream_router, prefix="/api/v1")

# Temporary debug endpoint for diagnosing empty track list rendering
from fastapi import Depends  # type: ignore
from sqlalchemy import select as _select  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore
try:
    from .db.session import get_session as _get_session  # type: ignore
    from .db.models.models import Track as _Track  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session as _get_session  # type: ignore
    from db.models.models import Track as _Track  # type: ignore

@app.get("/api/v1/_debug/track_count")
async def debug_track_count(session: AsyncSession = Depends(_get_session)):
    rows = (await session.execute(_select(_Track))).scalars().all()
    sample = []
    for t in rows[:3]:
        sample.append({
            "id": t.id,
            "title": t.title,
            "artists": t.artists,
            "created_at": str(t.created_at),
        })
    return {"count": len(rows), "sample": sample}


@app.get("/api")
def api_root():
    return {"name": settings.app_name, "version": settings.version}

# Convenience redirects for default FastAPI docs paths
@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/api/docs")

@app.get("/redoc", include_in_schema=False)
async def redoc_redirect():
    return RedirectResponse(url="/api/redoc")

# Static files (built frontend). When building the frontend, files will be placed under
# backend/app/static. We mount them at / and provide an SPA fallback.
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    # Serve static assets (JS, CSS, images, etc.)
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # SPA fallback: serve index.html for all non-API routes
    # This must be defined as a catch-all route to handle client-side routing
    from starlette.exceptions import HTTPException
    
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Don't intercept API routes - let FastAPI handle them and return proper 404
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        
        # Check if the requested file exists in static_dir (e.g., favicon.ico, robots.txt)
        requested_file = static_dir / full_path
        if requested_file.is_file():
            return FileResponse(str(requested_file))
        
        # For all other routes, serve index.html to let the frontend router handle it
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404, detail="Not Found")
