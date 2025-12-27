from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import shutil

try:  # package mode
    from ..core.config import settings  # type: ignore
    from ..db.session import async_session  # type: ignore
    from ..db.models.models import Download, DownloadStatus, Track, SearchCandidate, SearchProvider, LibraryFile, Playlist, PlaylistTrack, SourceProvider  # type: ignore
    from .log_buffer import download_logs  # type: ignore
except Exception:  # pragma: no cover
    from core.config import settings  # type: ignore
    from db.session import async_session  # type: ignore
    from db.models.models import Download, DownloadStatus, Track, SearchCandidate, SearchProvider, LibraryFile, Playlist, PlaylistTrack, SourceProvider  # type: ignore
    from utils.log_buffer import download_logs  # type: ignore


def _log(msg: str, level: str = "INFO") -> None:
    """Log to console and the in-memory log buffer."""
    print(f"[downloader] {msg}")
    download_logs.append(level, f"[downloader] {msg}")


@dataclass
class DownloadOutcome:
    filepath: Path
    format: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    filesize_bytes: Optional[int] = None
    checksum_sha256: Optional[str] = None


def _safe_filename(text: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180]


def _sanitize_component(name: str) -> str:
    """Sanitize a single path component for Windows."""
    s = re.sub(r"[\\/:*?\"<>|]+", "_", name or "")
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" .")


async def extract_audio_duration(filepath: Path) -> Optional[int]:
    """Extract actual audio duration in milliseconds using ffprobe.
    
    Returns:
        Duration in milliseconds, or None if extraction fails.
    """
    try:
        import json
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "format=duration", "-of", "json", str(filepath)
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        
        if proc.returncode == 0 and stdout:
            data = json.loads(stdout.decode())
            if isinstance(data, dict):
                fmt = data.get("format") or {}
                dur_str = fmt.get("duration")
                if isinstance(dur_str, str):
                    dur = float(dur_str)
                    if dur > 0:
                        return int(dur * 1000)
    except Exception:
        # Ignore ffprobe failures
        pass
    return None


async def _set_file_timestamps(file_path: Path, track: Track, track_id: int) -> None:
    """Set file timestamps based on track metadata and playlist context.
    
    Creation time: Track release_date (if available), otherwise current time
    Modification time: Most recent added_at from playlists (if available), otherwise current time
    
    Cross-platform implementation:
    - Linux/macOS: Sets modification and access time (creation time is filesystem-dependent)
    - Windows: Sets modification, access, and creation time (requires pywin32)
    """
    import time
    import platform
    
    # Get release date from track for creation time
    creation_time = None
    if track.release_date:
        creation_time = track.release_date.timestamp()
    
    # Get the most recent playlist added_at for modification time
    modification_time = None
    try:
        async with async_session() as session:
            from sqlalchemy import select, desc
            from ..db.models.models import PlaylistTrack  # type: ignore
            
            result = await session.execute(
                select(PlaylistTrack)
                .where(PlaylistTrack.track_id == track_id)
                .where(PlaylistTrack.added_at.isnot(None))
                .order_by(desc(PlaylistTrack.added_at))
            )
            latest_playlist_entry = result.scalars().first()
            if latest_playlist_entry and latest_playlist_entry.added_at:
                modification_time = latest_playlist_entry.added_at.timestamp()
    except Exception:
        pass  # If we can't get playlist info, use defaults
    
    # Fallback to current time if we don't have the dates
    current_time = time.time()
    if creation_time is None:
        creation_time = current_time
    if modification_time is None:
        modification_time = current_time
    
    # Ensure modification time is not before creation time
    if modification_time < creation_time:
        modification_time = creation_time
    
    # Set the timestamps - cross-platform approach
    try:
        # Always set access time and modification time (works on all platforms)
        await asyncio.to_thread(os.utime, file_path, (modification_time, modification_time))
        
        # Platform-specific creation time handling
        system = platform.system().lower()
        
        if system == "windows":
            # Windows: Try to set creation time with pywin32 (optional dependency)
            await _set_windows_creation_time(file_path, creation_time, modification_time)
        
        elif system == "darwin":
            # macOS: Try to set creation time with xattr (birth time)
            await _set_macos_creation_time(file_path, creation_time)
        
        elif system == "linux":
            # Linux: Creation time handling is filesystem-dependent
            # ext4, btrfs, etc. support birth time but it's not easily settable
            # We rely on the fact that the file was just created, so creation time should be recent
            pass
        
    except Exception:
        # If timestamp setting fails, continue without it (not critical)
        pass


async def _set_windows_creation_time(file_path: Path, creation_time: float, modification_time: float) -> None:
    """Set creation time on Windows using pywin32 (if available)."""
    try:
        import win32file
        import pywintypes
        
        def _set_creation_time():
            handle = win32file.CreateFile(
                str(file_path),
                win32file.GENERIC_WRITE,
                win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                None,
                win32file.OPEN_EXISTING,
                0,
                None
            )
            try:
                # Convert timestamp to Windows FILETIME
                creation_filetime = pywintypes.Time(creation_time)
                modification_filetime = pywintypes.Time(modification_time)
                win32file.SetFileTime(handle, creation_filetime, None, modification_filetime)
            finally:
                win32file.CloseHandle(handle)
        
        await asyncio.to_thread(_set_creation_time)
    except ImportError:
        # pywin32 not available - skip creation time setting
        pass
    except Exception:
        # Other error setting creation time - continue without it
        pass


async def _set_macos_creation_time(file_path: Path, creation_time: float) -> None:
    """Set creation time on macOS using subprocess (if available)."""
    try:
        import subprocess
        from datetime import datetime
        
        # Convert timestamp to macOS date format: MM/dd/yyyy HH:mm:ss
        dt = datetime.fromtimestamp(creation_time)
        date_str = dt.strftime("%m/%d/%Y %H:%M:%S")
        
        def _set_creation_time():
            # Use SetFile command (part of Xcode command line tools)
            subprocess.run([
                "SetFile", "-d", date_str, str(file_path)
            ], check=True, capture_output=True)
        
        await asyncio.to_thread(_set_creation_time)
    except (ImportError, subprocess.CalledProcessError, FileNotFoundError):
        # SetFile not available or failed - skip creation time setting
        pass
    except Exception:
        # Other error setting creation time - continue without it
        pass


async def _resolve_storage_context(session, track_id: int) -> tuple[str, Optional[str]]:
    """Return (provider_slug, playlist_name_or_None) for hierarchical storage.

    Rule:
    - If the track appears in any playlist, use that playlist's provider and name; only spotify keeps the playlist folder.
    - Otherwise return ("other", None).
    """
    try:
        from sqlalchemy import select as _select
        res = await session.execute(
            _select(Playlist.provider, Playlist.name)
            .join(PlaylistTrack, Playlist.id == PlaylistTrack.playlist_id)
            .where(PlaylistTrack.track_id == track_id)
            .limit(1)
        )
        row = res.first()
        if row:
            provider: SourceProvider = row[0]
            name: Optional[str] = row[1]
            prov_slug = str(provider.value if hasattr(provider, 'value') else provider).lower()
            if prov_slug == "spotify":
                return prov_slug, name or None
            return prov_slug, None
    except Exception:
        pass
    return "other", None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


async def _ensure_dir(path: Path) -> None:
    # Run in thread to avoid blocking
    def _mk():
        path.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_mk)


async def _write_fake_mp3(path: Path, title: str, artists: str) -> None:
    """Create a tiny placeholder .mp3 file for fake mode.

    We avoid external dependencies; this is not a valid audio stream but is sufficient
    for tests that only check for file existence and metadata persistence.
    """
    header = b"ID3" + b"\x03\x00\x00" + b"\x00\x00\x00\x00"  # minimal ID3 tag header
    payload = f"Fake audio for {artists} - {title}\n".encode("utf-8")
    data = header + payload
    def _write():
        with path.open("wb") as f:
            f.write(data)
    await asyncio.to_thread(_write)


async def _download_spotify_cover(cover_url: str, temp_dir: Path) -> Optional[Path]:
    """Download Spotify cover image to a temporary file and return the path.
    
    Returns None if download fails or URL is not provided.
    """
    if not cover_url:
        return None
    
    try:
        import httpx
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(cover_url)
            if response.status_code != 200:
                _log(f"Failed to download cover: HTTP {response.status_code}", "WARN")
                return None
            
            # Determine image extension from content-type or URL
            content_type = response.headers.get("content-type", "")
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "png" in content_type:
                ext = ".png"
            elif cover_url.endswith(".jpg") or cover_url.endswith(".jpeg"):
                ext = ".jpg"
            elif cover_url.endswith(".png"):
                ext = ".png"
            else:
                ext = ".jpg"  # default
            
            # Save to temporary file
            cover_path = temp_dir / f"cover{ext}"
            await asyncio.to_thread(cover_path.write_bytes, response.content)
            return cover_path
    except Exception as e:
        _log(f"Error downloading Spotify cover: {e}", "ERROR")
        return None


async def _embed_cover_image(audio_file: Path, cover_file: Path, ffmpeg_path: str) -> bool:
    """Embed cover image into audio file using ffmpeg.
    
    This creates a temporary file with the embedded cover, then replaces the original.
    Returns True if successful, False otherwise.
    """
    try:
        temp_output = audio_file.with_name(audio_file.stem + "_temp" + audio_file.suffix)
        
        # Build ffmpeg command to embed cover
        # For MP3: use -i for audio, -i for image, -map 0:a -map 1:0 -c copy -id3v2_version 3
        # For M4A: similar but with -disposition:v:0 attached_pic
        cmd = [
            ffmpeg_path,
            "-i", str(audio_file),
            "-i", str(cover_file),
            "-map", "0:a",
            "-map", "1:0",
            "-c", "copy",
        ]
        
        # Add format-specific flags
        if audio_file.suffix.lower() == ".mp3":
            cmd.extend(["-id3v2_version", "3", "-write_id3v1", "1"])
        elif audio_file.suffix.lower() in [".m4a", ".mp4"]:
            cmd.extend(["-disposition:v:0", "attached_pic"])
        
        cmd.extend(["-y", str(temp_output)])
        
        def _run_ffmpeg():
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                _log(f"ffmpeg embed cover failed: {result.stderr}", "ERROR")
                return False
            return True
        
        success = await asyncio.to_thread(_run_ffmpeg)
        if not success or not temp_output.exists():
            return False
        
        # Replace original file with the one that has embedded cover
        def _replace():
            if audio_file.exists():
                audio_file.unlink()
            temp_output.replace(audio_file)
        
        await asyncio.to_thread(_replace)
        _log(f"Successfully embedded Spotify cover into {audio_file.name}")
        return True
        
    except Exception as e:
        _log(f"Error embedding cover image: {e}", "ERROR")
        # Clean up temp file if it exists
        try:
            if temp_output.exists():
                await asyncio.to_thread(temp_output.unlink)
        except Exception:
            pass
        return False


def _resolve_extractor_args() -> Optional[str]:
    """Resolve the base extractor args from env/settings (may be overridden per retry profile)."""
    raw = os.environ.get("DOWNLOAD_YTDLP_EXTRACTOR_ARGS")
    if raw is None or raw.strip() == "":
        raw = getattr(settings, "download_extractor_args", None)
    if raw is None:
        return None
    normalized = raw.strip()
    if normalized.lower() in {"none", "off", "false", "0"}:
        return None
    return normalized


def _build_retry_profiles(base_extractor: Optional[str]) -> list[Optional[str]]:
    """Build an ordered list of extractor-args overrides to try.

    Goal: behave like desktop browser first (web) and progressively widen.
    Default order (when android present or user wants desktop behavior):
        web -> web_embedded -> tv -> auto (None)

    If base extractor args does NOT specify player_client we keep it as first profile to respect user config.
    Users can override ordering via DOWNLOAD_RETRY_PROFILES CSV tokens.

    Supported tokens -> extractor args:
      web        : youtube:player_client=web
      web_embed  : youtube:player_client=web_embedded,web
      tv         : youtube:player_client=tv,web
      auto       : None (let yt-dlp decide)
      android    : youtube:player_client=android,web  (not recommended without PO token)
    """
    override_csv = os.environ.get("DOWNLOAD_RETRY_PROFILES")
    token_map: dict[str, Optional[str]] = {
        "web": "youtube:player_client=web",
        "web_embed": "youtube:player_client=web_embedded,web",
        "tv": "youtube:player_client=tv,web",
        "auto": None,
        "android": "youtube:player_client=android,web",
    }
    profiles: list[Optional[str]] = []
    if override_csv:
        for tok in [t.strip() for t in override_csv.split(",") if t.strip()]:
            arg = token_map.get(tok)
            if tok not in token_map:
                continue
            if arg not in profiles:
                profiles.append(arg)
        if not profiles:
            profiles = [None]
        return profiles
    # Auto-build
    base_has_client = bool(base_extractor and "player_client=" in base_extractor)
    if not base_has_client and base_extractor:
        # Use user supplied first, then fallback to auto
        profiles.append(base_extractor)
        profiles.append(None)
        return profiles
    # Android present or explicit multi client: prefer desktop-like first
    for arg in ("youtube:player_client=web", "youtube:player_client=web_embedded,web", "youtube:player_client=tv,web", None):
        profiles.append(arg)
    return profiles
    
def _resolve_extra_args() -> list[str]:
    """Resolve additional yt-dlp CLI arguments from env YT_DLP_EXTRA_ARGS."""
    raw = os.environ.get("YT_DLP_EXTRA_ARGS", "")
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        import shlex
        return shlex.split(raw)
    except Exception:
        # Fallback split if shlex fails due to quotes on some platforms
        return [p for p in raw.split() if p]


def _build_ytdlp_command(
    ytdlp_path: str,
    ffmpeg_path: str,
    tmp_out: Path,
    url: str,
    audio_fmt: str,
    allow_embed: bool,
    add_metadata: bool,
    embed_thumb: bool,
    clean_tags: bool,
    metadata_args: list[str],
    extractor_override: Optional[str] = None,
) -> list[str]:
    parts: list[str] = [
        ytdlp_path,
        "-x", "--audio-format", audio_fmt,
        "--ffmpeg-location", ffmpeg_path,
    ]
    if add_metadata:
        parts.append("--add-metadata")
    if allow_embed and embed_thumb:
        parts.append("--embed-thumbnail")
    extractor_args = extractor_override if extractor_override is not None else _resolve_extractor_args()
    if extractor_args:
        parts.extend(["--extractor-args", extractor_args])
    # Append any global extra args from env (e.g., --force-ipv4 -f bestaudio ...)
    extra_args = _resolve_extra_args()
    if extra_args:
        parts.extend(extra_args)
    fmt_flags: list[str] = []
    if clean_tags:
        fmt_flags += ["-map_metadata", "-1"]
    if audio_fmt.lower() == "mp3":
        fmt_flags += ["-id3v2_version", "3", "-write_id3v1", "1"]
    ff_args = " ".join(fmt_flags + metadata_args)
    parts.extend(["--ppa", f"ffmpeg:{ff_args}"])
    parts.extend(["-o", str(tmp_out) + ".%(ext)s", url])
    return parts


async def perform_download(download_id: int) -> DownloadOutcome:
    """Perform the download for a Download row and return outcome.

    Behavior:
    - If env DOWNLOAD_FAKE=1, create a small placeholder file.
    - Else use yt-dlp to download best audio; requires yt-dlp/ffmpeg available.
    """
    async with async_session() as session:
        dl = await session.get(Download, download_id)
        if not dl:
            raise RuntimeError("Download row not found")
        track = await session.get(Track, dl.track_id)
        if not track:
            raise RuntimeError("Track not found")
        cand: Optional[SearchCandidate] = None
        if dl.candidate_id:
            cand = await session.get(SearchCandidate, dl.candidate_id)
        if not cand:
            # fallback to chosen youtube candidate if present
            from sqlalchemy import select, desc
            result = await session.execute(
                select(SearchCandidate)
                .where(SearchCandidate.track_id == dl.track_id)
                .order_by(desc(SearchCandidate.chosen), desc(SearchCandidate.score))
            )
            cand = result.scalars().first()
        # Try to find an existing library file for this track to overwrite
        prev_lf_path: Optional[Path] = None
        try:
            from sqlalchemy import select as _select, desc as _desc
            res_prev = await session.execute(_select(LibraryFile).where(LibraryFile.track_id == dl.track_id).order_by(_desc(LibraryFile.file_mtime)))
            prev_lf = res_prev.scalars().first()
            if prev_lf and prev_lf.filepath:
                prev_lf_path = Path(prev_lf.filepath)
        except Exception:
            prev_lf_path = None

    # Determine target directory and filename (hierarchical)
    # Allow runtime override via environment for tests; fallback to settings
    lib_dir_env = os.environ.get("LIBRARY_DIR")
    lib_dir = Path(lib_dir_env or settings.library_dir).resolve()
    await _ensure_dir(lib_dir)
    # Storage context (provider/playlist)
    async with async_session() as _s2:
        prov_slug, playlist_name = await _resolve_storage_context(_s2, track.id)
    artists_safe = _sanitize_component(track.artists or "Unknown Artist")
    title_safe = _sanitize_component(track.title or "Unknown Title")
    # Default extension preferred
    ext = ".mp3"
    # Build hierarchical path
    if playlist_name:
        out_path = lib_dir / _sanitize_component(prov_slug) / _sanitize_component(playlist_name) / f"{artists_safe} - {title_safe}{ext}"
    else:
        out_path = lib_dir / _sanitize_component(prov_slug) / f"{artists_safe} - {title_safe}{ext}"
    # If we have a previous library file for this track, prefer overwriting that exact file (to avoid duplicates)
    if prev_lf_path is not None:
        out_path = prev_lf_path
    await _ensure_dir(out_path.parent)

    # Fake mode
    if os.environ.get("DOWNLOAD_FAKE", "0") in {"1", "true", "TRUE", "True"}:
        _log(f"FAKE mode -> creating placeholder at {out_path}")
        # Overwrite existing file if present
        try:
            if out_path.exists():
                await asyncio.to_thread(out_path.unlink)
        except Exception:
            pass
        await _write_fake_mp3(out_path, title=track.title, artists=track.artists)
        
        # Set file timestamps based on track metadata and playlist context
        await _set_file_timestamps(out_path, track, dl.track_id)
        
        checksum = _sha256_file(out_path)
        size = out_path.stat().st_size
        return DownloadOutcome(filepath=out_path, format="mp3", bitrate_kbps=None, filesize_bytes=size, checksum_sha256=checksum)

    # Real mode with yt-dlp; build command
    if not cand or (cand.provider != SearchProvider.youtube):
        raise RuntimeError("A YouTube candidate is required for yt-dlp download")
    # Resolve executables robustly across Windows/Unix
    def _resolve_exec(config_value: Optional[str], exe_names: list[str]) -> Optional[str]:
        """Return absolute path to executable if found, else None.

        Search order:
        1) If config_value provided: try as absolute; if relative, try relative to project root and backend root and CWD.
        2) Typical venv locations under project/ and backend/ (.venv, venv).
        3) PATH lookup via shutil.which for each exe name.
        """
        project_root = Path(__file__).resolve().parents[3]
        backend_root = Path(__file__).resolve().parents[2]

        candidates: list[Path] = []
        if config_value:
            p = Path(config_value)
            candidates.append(p if p.is_absolute() else (project_root / p))
            if not p.is_absolute():
                candidates.append(backend_root / p)
                candidates.append(Path.cwd() / p)
        # Typical venvs
        for root in (project_root, backend_root):
            for vname in (".venv", "venv"):  # common names
                for sub in ("Scripts", "bin"):
                    for n in exe_names:
                        candidates.append(root / vname / sub / n)

        for cand in candidates:
            try:
                if cand.exists():
                    return str(cand.resolve())
            except Exception:
                pass
        for n in exe_names:
            which = shutil.which(n)
            if which:
                return which
        return None

    ytdlp_path = _resolve_exec(settings.yt_dlp_bin, ["yt-dlp.exe", "yt-dlp"]) or settings.yt_dlp_bin or "yt-dlp"
    ffmpeg_path = _resolve_exec(settings.ffmpeg_bin, ["ffmpeg.exe", "ffmpeg"]) or settings.ffmpeg_bin or "ffmpeg"
    # Template: bestaudio -> preferred format using ffmpeg, write to out_path (extension added by yt-dlp)
    # Let yt-dlp decide extension via template; we'll detect and rename if needed
    # Use the same base name so re-download replaces previous file (possibly with new extension)
    tmp_out = out_path.with_suffix("")
    # Quote values to survive spaces/special chars (yt-dlp will parse with shlex)
    def _q(v: Optional[str]) -> str:
        if v is None:
            return ""
        # Use double quotes around value; replace internal quotes with single quotes
        return '"' + str(v).replace('"', "'") + '"'
    pp_args = [
        f"-metadata artist={_q(track.artists)}",
        f"-metadata title={_q(track.title)}",
    ]
    if track.album:
        pp_args.append(f"-metadata album={_q(track.album)}")
    # Add release date metadata
    if track.release_date:
        release_date_str = track.release_date.strftime("%Y-%m-%d")
        release_year = track.release_date.strftime("%Y")
        # GROUPING tag with full date (YYYY-MM-DD)
        pp_args.append(f"-metadata grouping={_q(release_date_str)}")  # generic/m4a
        pp_args.append(f"-metadata TIT1={_q(release_date_str)}")      # ID3v2 (mp3)
        # Year/Date tags
        pp_args.append(f"-metadata date={_q(release_date_str)}")      # ISO date (generic)
        pp_args.append(f"-metadata year={_q(release_year)}")          # year (generic)
        pp_args.append(f"-metadata TDRC={_q(release_date_str)}")      # ID3v2 recording time
        pp_args.append(f"-metadata TYER={_q(release_year)}")          # ID3v2 year (legacy)
    # Optional metadata
    try:
        if getattr(track, "genre", None):
            pp_args.append(f"-metadata genre={_q(track.genre)}")
        if getattr(track, "bpm", None):
            bpm_val = str(track.bpm)
            # Set multiple keys for better cross-format support
            pp_args.append(f"-metadata TBPM={_q(bpm_val)}")  # ID3v2 (mp3)
            pp_args.append(f"-metadata bpm={_q(bpm_val)}")   # generic
            pp_args.append(f"-metadata tempo={_q(bpm_val)}") # mp4/m4a (tmpo)
    except Exception:
        pass
    post_args = " ".join(pp_args)
    # Controls
    # - DOWNLOAD_ADD_SOURCE_METADATA: if true, pass yt-dlp --add-metadata (YouTube source tags)
    # - DOWNLOAD_CLEAN_TAGS: if true, drop all existing tags before writing ours
    # - DOWNLOAD_EMBED_THUMBNAIL: embed cover image when supported
    ytdlp_add_meta = os.environ.get("DOWNLOAD_ADD_SOURCE_METADATA", "0") not in {"0", "false", "False", "FALSE"}
    clean_tags = os.environ.get("DOWNLOAD_CLEAN_TAGS", "1") not in {"0", "false", "False", "FALSE"}
    embed_thumb = os.environ.get("DOWNLOAD_EMBED_THUMBNAIL", "1") not in {"0", "false", "False", "FALSE"}
    
    # Disable YouTube thumbnail embedding if we have a Spotify cover (we'll embed it separately)
    has_spotify_cover = track.cover_url and track.cover_url.startswith("https://i.scdn.co/")
    if has_spotify_cover:
        embed_thumb = False

    def build_cmd(audio_fmt: str, allow_embed: bool = True) -> list[str]:
        return _build_ytdlp_command(
            ytdlp_path=ytdlp_path,
            ffmpeg_path=ffmpeg_path,
            tmp_out=tmp_out,
            url=cand.url,
            audio_fmt=audio_fmt,
            allow_embed=allow_embed,
            add_metadata=ytdlp_add_meta,
            embed_thumb=embed_thumb,
            clean_tags=clean_tags,
            metadata_args=pp_args,
        )

    base_extractor = _resolve_extractor_args()
    profiles = _build_retry_profiles(base_extractor)
    preferred_fmt = settings.preferred_audio_format.lower()
    last_error: Optional[Exception] = None

    def _run_profile(extractor_override: Optional[str]) -> bool:
        nonlocal last_error
        # Build initial command (preferred fmt)
        cmd_local = _build_ytdlp_command(
            ytdlp_path=ytdlp_path,
            ffmpeg_path=ffmpeg_path,
            tmp_out=tmp_out,
            url=cand.url,
            audio_fmt=preferred_fmt,
            allow_embed=True,
            add_metadata=ytdlp_add_meta,
            embed_thumb=embed_thumb,
            clean_tags=clean_tags,
            metadata_args=pp_args,
            extractor_override=extractor_override,
        )
        _log(f"Using yt-dlp={ytdlp_path} ffmpeg={ffmpeg_path}")
        _log(f"Profile extractor_args={extractor_override or 'AUTO'} cmd: {' '.join(shlex.quote(c) for c in cmd_local)}")
        try:
            res = subprocess.run(cmd_local, check=True, capture_output=True, text=True)
            if res.stdout:
                for line in res.stdout.strip().split("\n"):
                    if line.strip():
                        _log(f"yt-dlp: {line.strip()}")
            return True
        except FileNotFoundError as e:
            _log(f"Executable not found: {e.filename}", "ERROR")
            raise RuntimeError(f"Executable not found: {e.filename}. Check YT_DLP_BIN/FFMPEG_BIN or PATH.") from e
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            if stderr:
                for line in stderr.strip().split("\n"):
                    if line.strip():
                        _log(f"yt-dlp error: {line.strip()}", "ERROR")
            sabr_hint = any(k in stderr for k in ["SABR", "Did not get any data blocks", "po token", "missing a url"])
            # Try m4a fallback if mp3 preferred
            if preferred_fmt == "mp3":
                alt_cmd = _build_ytdlp_command(
                    ytdlp_path=ytdlp_path,
                    ffmpeg_path=ffmpeg_path,
                    tmp_out=tmp_out,
                    url=cand.url,
                    audio_fmt="m4a",
                    allow_embed=True,
                    add_metadata=ytdlp_add_meta,
                    embed_thumb=embed_thumb,
                    clean_tags=clean_tags,
                    metadata_args=pp_args,
                    extractor_override=extractor_override,
                )
                _log("mp3 failed; retrying same profile with m4a", "WARN")
                _log(f"Running: {' '.join(shlex.quote(c) for c in alt_cmd)}")
                try:
                    res2 = subprocess.run(alt_cmd, check=True, capture_output=True, text=True)
                    if res2.stdout:
                        for line in res2.stdout.strip().split("\n"):
                            if line.strip():
                                _log(f"yt-dlp: {line.strip()}")
                    return True
                except subprocess.CalledProcessError as e2:
                    stderr2 = e2.stderr or ""
                    if stderr2:
                        for line in stderr2.strip().split("\n"):
                            if line.strip():
                                _log(f"yt-dlp error: {line.strip()}", "ERROR")
                    sabr_hint = sabr_hint or any(k in stderr2 for k in ["SABR", "Did not get any data blocks", "po token", "missing a url"])
                    if sabr_hint:
                        last_error = e2
                        return False  # move to next profile
                    last_error = e2
                    raise
            if sabr_hint:
                last_error = e
                return False  # try next profile
            last_error = e
            raise

    # Iterate profiles
    for idx, prof in enumerate(profiles, start=1):
        _log(f"Trying profile {idx}/{len(profiles)} extractor_args={prof or 'AUTO'}")
        success = await asyncio.to_thread(_run_profile, prof)
        if success:
            break
    else:
        # Exhausted profiles, raise last error if any
        if last_error:
            raise last_error
        raise RuntimeError("Download failed after all profiles without explicit error captured")
    # Determine actual output file produced
    produced = None
    for ext_try in (".mp3", ".m4a", ".opus", ".webm"):
        p = Path(str(tmp_out) + ext_try)
        if p.exists():
            produced = p
            break
    if not produced:
        # Fallback: if out_path exists
        if out_path.exists():
            produced = out_path
        else:
            raise RuntimeError("yt-dlp did not produce an output file")
    # If produced name differs, move to final out_path (keeping extension) and remove previous file if extension changed
    if produced != out_path:
        final_path = out_path.with_suffix(produced.suffix)
        # Remove existing target file to ensure overwrite (no (1) suffixes)
        try:
            if final_path.exists():
                await asyncio.to_thread(final_path.unlink)
        except Exception:
            pass
        def _rename():
            _log(f"Renaming {produced} -> {final_path}")
            produced.replace(final_path)
        await asyncio.to_thread(_rename)
        # If there was an older library file with a different extension, remove it to avoid duplicates
        try:
            if prev_lf_path and prev_lf_path.exists() and prev_lf_path != final_path:
                await asyncio.to_thread(prev_lf_path.unlink)
        except Exception:
            pass
        out_path = final_path

    size = out_path.stat().st_size
    checksum = _sha256_file(out_path)
    fmt = out_path.suffix.lstrip(".")
    
    # Embed Spotify cover image if available (prioritize over YouTube thumbnail)
    if track.cover_url and track.cover_url.startswith("https://i.scdn.co/"):
        # This is a Spotify cover URL
        try:
            cover_file = await _download_spotify_cover(track.cover_url, out_path.parent)
            if cover_file:
                ffmpeg_path = _resolve_exec(settings.ffmpeg_bin, ["ffmpeg.exe", "ffmpeg"]) or settings.ffmpeg_bin or "ffmpeg"
                embed_success = await _embed_cover_image(out_path, cover_file, ffmpeg_path)
                # Clean up the temporary cover file
                try:
                    await asyncio.to_thread(cover_file.unlink)
                except Exception:
                    pass
                # Recalculate checksum and size after embedding cover
                if embed_success:
                    size = out_path.stat().st_size
                    checksum = _sha256_file(out_path)
        except Exception as e:
            _log(f"Failed to embed Spotify cover: {e}", "ERROR")
    
    # Set file timestamps based on track metadata and playlist context
    await _set_file_timestamps(out_path, track, dl.track_id)
    
    return DownloadOutcome(filepath=out_path, format=fmt, bitrate_kbps=None, filesize_bytes=size, checksum_sha256=checksum)
