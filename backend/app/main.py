from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from typing import List, Dict, Any

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
    from .api.v1.oauth import router as oauth_router  # type: ignore
    from .api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from .db.session import engine, Base  # type: ignore
    from .core.config import settings  # type: ignore
    from .api.v1.downloads import router as downloads_router  # type: ignore
    from .api.v1.library import router as library_router  # type: ignore
    from .worker.downloads_worker import download_queue, DownloadQueue  # type: ignore
except Exception:  # pragma: no cover
    from api.v1.health import router as health_router  # type: ignore
    from api.v1.sources import router as sources_router  # type: ignore
    from api.v1.playlists import router as playlists_router  # type: ignore
    from api.v1.tracks import router as tracks_router  # type: ignore
    from api.v1.tracks_import import router as tracks_import_router  # type: ignore
    from api.v1.identities import router as identities_router  # type: ignore
    from api.v1.candidates import router as candidates_router  # type: ignore
    from api.v1.oauth import router as oauth_router  # type: ignore
    from api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from db.session import engine, Base  # type: ignore
    from core.config import settings  # type: ignore
    from api.v1.downloads import router as downloads_router  # type: ignore
    from api.v1.library import router as library_router  # type: ignore
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

        # (Removed: audio feature columns auto-migration no longer needed)

    # Start download worker(s) unless disabled (e.g., in tests)
    import os
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
app.include_router(oauth_router, prefix="/api/v1")
app.include_router(oauth_spotify_router, prefix="/api/v1")
app.include_router(downloads_router, prefix="/api/v1")
app.include_router(library_router, prefix="/api/v1")

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
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")

    # Optional explicit fallback for SPA routes not starting with /api
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):  # type: ignore[unused-argument]
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"detail": "Not Found"}
