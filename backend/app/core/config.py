from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel


# Load environment variables from a .env file located at backend/.env (or project root)
# This does not override already-set environment variables.
load_dotenv()


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    app_name: str = os.environ.get("APP_NAME", "Music Downloader API")
    version: str = os.environ.get("APP_VERSION", "0.1.0")

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


settings = Settings()
