from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel

try:
    # Package-relative (when imported as backend.app.schemas.models)
    from ..db.models.models import (
        SourceProvider,
        SearchProvider,
        DownloadProvider,
        DownloadStatus,
    )
except Exception:  # pragma: no cover
    try:
        # Flat mode (when backend/app is on sys.path)
        from db.models.models import (
            SourceProvider,
            SearchProvider,
            DownloadProvider,
            DownloadStatus,
        )
    except Exception:  # pragma: no cover
        # Fully qualified absolute import as last resort
        from backend.app.db.models.models import (
            SourceProvider,
            SearchProvider,
            DownloadProvider,
            DownloadStatus,
        )


class SourceAccountCreate(BaseModel):
    type: SourceProvider
    name: str
    enabled: bool = True
    config_json: Optional[str] = None


class SourceAccountRead(SourceAccountCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlaylistCreate(BaseModel):
    provider: SourceProvider
    name: str
    source_account_id: Optional[int] = None
    provider_playlist_id: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    snapshot: Optional[str] = None
    selected: bool = False


class PlaylistRead(PlaylistCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrackCreate(BaseModel):
    title: str
    artists: str
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    year: Optional[int] = None
    explicit: bool = False
    cover_url: Optional[str] = None
    normalized_title: Optional[str] = None
    normalized_artists: Optional[str] = None
    genre: Optional[str] = None
    bpm: Optional[int] = None


class TrackRead(TrackCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrackIdentityCreate(BaseModel):
    track_id: int
    provider: SourceProvider
    provider_track_id: str
    provider_url: Optional[str] = None
    fingerprint: Optional[str] = None


class TrackIdentityRead(TrackIdentityCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrackIdentityFilters(BaseModel):
    track_id: Optional[int] = None
    has_fingerprint: Optional[bool] = None
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None


class PlaylistTrackCreate(BaseModel):
    playlist_id: int
    track_id: int
    position: Optional[int] = None
    added_at: Optional[datetime] = None


class PlaylistTrackRead(PlaylistTrackCreate):
    id: int

    class Config:
        from_attributes = True


class SearchCandidateCreate(BaseModel):
    track_id: int
    provider: SearchProvider
    external_id: str
    url: str
    title: str
    channel: Optional[str] = None
    duration_sec: Optional[int] = None
    score: float
    chosen: bool = False


class SearchCandidateRead(SearchCandidateCreate):
    id: int
    created_at: datetime
    duration_delta_sec: Optional[float] = None  # computed client convenience
    class ScoreBreakdown(BaseModel):
        text: float
        duration: float
        extended: float
        channel: float
        penalty: float  # aggregated: tokens_penalty + keywords_penalty
        total: float

    score_breakdown: Optional[ScoreBreakdown] = None

    class Config:
        from_attributes = True


class DownloadCreate(BaseModel):
    track_id: int
    candidate_id: Optional[int] = None
    provider: DownloadProvider
    status: DownloadStatus
    filepath: Optional[str] = None
    format: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    filesize_bytes: Optional[int] = None
    checksum_sha256: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class DownloadRead(DownloadCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class LibraryFileCreate(BaseModel):
    track_id: int
    filepath: str
    file_mtime: datetime
    file_size: int
    checksum_sha256: Optional[str] = None
    exists: bool = True


class LibraryFileRead(LibraryFileCreate):
    id: int

    class Config:
        from_attributes = True


# OAuth token DTOs (refresh token handled encrypted at persistence layer)
class OAuthTokenCreate(BaseModel):
    source_account_id: int
    provider: SourceProvider
    access_token: str
    refresh_token: Optional[str] = None  # plaintext in request body
    scope: Optional[str] = None
    token_type: Optional[str] = None
    expires_at: Optional[datetime] = None


class OAuthTokenRead(BaseModel):
    id: int
    source_account_id: int
    provider: SourceProvider
    access_token: str
    scope: Optional[str] = None
    token_type: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OAuthStateRead(BaseModel):
    id: int
    provider: SourceProvider
    source_account_id: int
    state: str
    redirect_to: Optional[str] = None
    created_at: datetime
    used_at: Optional[datetime] = None
    consumed: bool

    class Config:
        from_attributes = True
