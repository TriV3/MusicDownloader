from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Support both execution modes:
# - "uvicorn backend.app.main:app" (package-relative imports)
# - "uvicorn main:app" with sys.path pointing to backend/app (flat imports)
try:
    from .api.v1.health import router as health_router  # type: ignore
    from .api.v1.sources import router as sources_router  # type: ignore
    from .api.v1.playlists import router as playlists_router  # type: ignore
    from .api.v1.tracks import router as tracks_router  # type: ignore
    from .api.v1.oauth import router as oauth_router  # type: ignore
    from .api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from .db.session import engine, Base  # type: ignore
except Exception:  # pragma: no cover
    from api.v1.health import router as health_router  # type: ignore
    from api.v1.sources import router as sources_router  # type: ignore
    from api.v1.playlists import router as playlists_router  # type: ignore
    from api.v1.tracks import router as tracks_router  # type: ignore
    from api.v1.oauth import router as oauth_router  # type: ignore
    from api.v1.oauth_spotify import router as oauth_spotify_router  # type: ignore
    from db.session import engine, Base  # type: ignore

app = FastAPI(title="Music Downloader API", version="0.1.0")

# CORS: autoriser le front Vite en dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    # Create tables (simple init, replace by migrations later)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Routes
app.include_router(health_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")
app.include_router(playlists_router, prefix="/api/v1")
app.include_router(tracks_router, prefix="/api/v1")
app.include_router(oauth_router, prefix="/api/v1")
app.include_router(oauth_spotify_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"name": "Music Downloader API", "version": "0.1.0"}
