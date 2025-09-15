from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel
try:
    from ..app_meta import __version__, __app_name__  # type: ignore
except Exception:  # pragma: no cover
    from app_meta import __version__, __app_name__  # type: ignore


# Load environment variables from a .env file located at backend/.env (or project root)
# This does not override already-set environment variables.
load_dotenv()


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


settings = Settings()
