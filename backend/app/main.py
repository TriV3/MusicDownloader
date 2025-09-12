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
    from .api.v1.identities import router as identities_router  # type: ignore
    from .api.v1.candidates import router as candidates_router  # type: ignore
    from .api.v1.oauth import router as oauth_router  # type: ignore
    from .api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from .db.session import engine, Base  # type: ignore
    from .core.config import settings  # type: ignore
except Exception:  # pragma: no cover
    from api.v1.health import router as health_router  # type: ignore
    from api.v1.sources import router as sources_router  # type: ignore
    from api.v1.playlists import router as playlists_router  # type: ignore
    from api.v1.tracks import router as tracks_router  # type: ignore
    from api.v1.identities import router as identities_router  # type: ignore
    from api.v1.candidates import router as candidates_router  # type: ignore
    from api.v1.oauth import router as oauth_router  # type: ignore
    from api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from db.session import engine, Base  # type: ignore
    from core.config import settings  # type: ignore

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

# Routes
app.include_router(health_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")
app.include_router(playlists_router, prefix="/api/v1")
app.include_router(tracks_router, prefix="/api/v1")
app.include_router(identities_router, prefix="/api/v1")
app.include_router(candidates_router, prefix="/api/v1")
app.include_router(oauth_router, prefix="/api/v1")
app.include_router(oauth_spotify_router, prefix="/api/v1")


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
