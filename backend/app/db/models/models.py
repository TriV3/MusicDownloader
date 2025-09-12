from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Float,
    UniqueConstraint,
    Index,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..session import Base


class SourceProvider(str, Enum):
    spotify = "spotify"
    soundcloud = "soundcloud"
    manual = "manual"


class SearchProvider(str, Enum):
    youtube = "youtube"
    ytmusic = "ytmusic"
    other = "other"


class DownloadProvider(str, Enum):
    yt_dlp = "yt_dlp"


class DownloadStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"
    already = "already"


class SourceAccount(Base):
    __tablename__ = "source_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[SourceProvider] = mapped_column(SAEnum(SourceProvider), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("type", "name", name="uq_source_type_name"),
    )


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("source_accounts.id"))
    provider: Mapped[SourceProvider] = mapped_column(SAEnum(SourceProvider), nullable=False)
    provider_playlist_id: Mapped[Optional[str]] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner: Mapped[Optional[str]] = mapped_column(String(200))
    snapshot: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    source_account: Mapped[Optional[SourceAccount]] = relationship(backref="playlists")

    __table_args__ = (
        UniqueConstraint("provider", "provider_playlist_id", name="uq_provider_playlist"),
    )


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artists: Mapped[str] = mapped_column(String(500), nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String(500))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    isrc: Mapped[Optional[str]] = mapped_column(String(50))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    explicit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cover_url: Mapped[Optional[str]] = mapped_column(String(1000))
    normalized_title: Mapped[str] = mapped_column(String(500), index=True)
    normalized_artists: Mapped[str] = mapped_column(String(500), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_track_isrc", "isrc"),
    )


class TrackIdentity(Base):
    __tablename__ = "track_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    provider: Mapped[SourceProvider] = mapped_column(SAEnum(SourceProvider), nullable=False)
    provider_track_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_url: Mapped[Optional[str]] = mapped_column(String(1000))
    fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    track: Mapped[Track] = relationship(backref="identities")

    __table_args__ = (
        UniqueConstraint("provider", "provider_track_id", name="uq_provider_track"),
        Index("ix_identity_track", "track_id"),
        Index("ix_identity_provider_track", "provider", "track_id"),
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    position: Mapped[Optional[int]] = mapped_column(Integer)
    added_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    playlist: Mapped[Playlist] = relationship(backref="playlist_tracks")
    track: Mapped[Track] = relationship(backref="playlist_entries")

    __table_args__ = (
        UniqueConstraint("playlist_id", "track_id", name="uq_playlist_track"),
        Index("ix_playlist_pos", "playlist_id", "position"),
    )


class SearchCandidate(Base):
    __tablename__ = "search_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    provider: Mapped[SearchProvider] = mapped_column(SAEnum(SearchProvider), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    channel: Mapped[Optional[str]] = mapped_column(String(300))
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    chosen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    track: Mapped[Track] = relationship(backref="candidates")

    __table_args__ = (
        UniqueConstraint("track_id", "provider", "external_id", name="uq_candidate_unique"),
        Index("ix_candidate_track_score", "track_id", "score"),
    )


class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("search_candidates.id"))
    provider: Mapped[DownloadProvider] = mapped_column(SAEnum(DownloadProvider), nullable=False)
    status: Mapped[DownloadStatus] = mapped_column(SAEnum(DownloadStatus), nullable=False)
    filepath: Mapped[Optional[str]] = mapped_column(String(1000))
    format: Mapped[Optional[str]] = mapped_column(String(50))
    bitrate_kbps: Mapped[Optional[int]] = mapped_column(Integer)
    filesize_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    track: Mapped[Track] = relationship(backref="downloads")
    candidate: Mapped[Optional[SearchCandidate]] = relationship()

    __table_args__ = (
        Index("ix_download_status", "status"),
        Index("ix_download_created_at", "created_at"),
    )


class LibraryFile(Base):
    __tablename__ = "library_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    filepath: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_mtime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(100))
    exists: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    track: Mapped[Track] = relationship(backref="files")

    __table_args__ = (
        UniqueConstraint("filepath", name="uq_library_filepath"),
        Index("ix_library_track", "track_id"),
    )


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_account_id: Mapped[int] = mapped_column(ForeignKey("source_accounts.id"), nullable=False)
    provider: Mapped[SourceProvider] = mapped_column(SAEnum(SourceProvider), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(String(500))
    token_type: Mapped[Optional[str]] = mapped_column(String(50))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    account: Mapped[SourceAccount] = relationship(backref="tokens")

    __table_args__ = (
        Index("ix_oauth_account", "source_account_id"),
        Index("ix_oauth_provider", "provider"),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[SourceProvider] = mapped_column(SAEnum(SourceProvider), nullable=False)
    source_account_id: Mapped[int] = mapped_column(ForeignKey("source_accounts.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(200), nullable=False)
    redirect_to: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    account: Mapped[SourceAccount] = relationship()

    __table_args__ = (
        Index("ix_oauthstate_state", "state"),
    )
