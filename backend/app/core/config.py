from __future__ import annotations

import os
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel
try:
    from ..app_meta import __version__, __app_name__  # type: ignore
except Exception:  # pragma: no cover
    from app_meta import __version__, __app_name__  # type: ignore


# Load environment variables from .env files without overriding existing env vars.
# Priority: backend/.env first (co-located with app), then project-root/.env as fallback.
from pathlib import Path
_backend_env = Path(__file__).resolve().parents[2] / ".env"
_root_env = Path(__file__).resolve().parents[3] / ".env"
# Load backend/.env if present
load_dotenv(dotenv_path=str(_backend_env), override=False)
# Load root/.env if present (values already set are not overridden)
load_dotenv(dotenv_path=str(_root_env), override=False)


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    # Name is sourced from code, not environment
    app_name: str = __app_name__
    # Version is sourced from code, not environment
    version: str = __version__

    # CORS
    cors_origins: List[str] = _split_csv(os.environ.get("CORS_ORIGINS")) or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Database and crypto
    database_url: str = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./music.db")
    secret_key: str = os.environ.get("SECRET_KEY", "")

    # Spotify OAuth
    spotify_client_id: str | None = os.environ.get("SPOTIFY_CLIENT_ID")
    spotify_client_secret: str | None = os.environ.get("SPOTIFY_CLIENT_SECRET")
    spotify_redirect_uri: str | None = os.environ.get("SPOTIFY_REDIRECT_URI")

    # YouTube search (Step 2.1)
    youtube_search_limit: int = int(os.environ.get("YOUTUBE_SEARCH_LIMIT", "8"))
    # When set (env only) YOUTUBE_SEARCH_FAKE=1 forces fake results (handled in utils.youtube_search)

    # Downloads (Step 2.3)
    # Default library under project root (one level above backend/)
    library_dir: str = os.environ.get("LIBRARY_DIR", str((__import__('pathlib').Path(__file__).resolve().parents[3] / "library").resolve()))
    yt_dlp_bin: Optional[str] = os.environ.get("YT_DLP_BIN") or None
    ffmpeg_bin: Optional[str] = os.environ.get("FFMPEG_BIN") or None
    preferred_audio_format: str = os.environ.get("PREFERRED_AUDIO_FORMAT", "mp3")


settings = Settings()
