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
    from ..db.models.models import Download, DownloadStatus, Track, SearchCandidate, SearchProvider, LibraryFile  # type: ignore
except Exception:  # pragma: no cover
    from core.config import settings  # type: ignore
    from db.session import async_session  # type: ignore
    from db.models.models import Download, DownloadStatus, Track, SearchCandidate, SearchProvider, LibraryFile  # type: ignore


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

    # Determine target directory and filename
    # Allow runtime override via environment for tests; fallback to settings
    lib_dir_env = os.environ.get("LIBRARY_DIR")
    lib_dir = Path(lib_dir_env or settings.library_dir).resolve()
    await _ensure_dir(lib_dir)
    base_name = _safe_filename(f"{track.artists} - {track.title}")
    # Prefer mp3 container by default
    ext = ".mp3"
    # Overwrite policy: if we have a previous library file for this track, target that path base; otherwise use default
    if prev_lf_path is not None:
        out_path = prev_lf_path
    else:
        out_path = lib_dir / f"{base_name}{ext}"

    # Fake mode
    if os.environ.get("DOWNLOAD_FAKE", "0") in {"1", "true", "TRUE", "True"}:
        print(f"[downloader] FAKE mode -> creating placeholder at {out_path}")
        # Overwrite existing file if present
        try:
            if out_path.exists():
                await asyncio.to_thread(out_path.unlink)
        except Exception:
            pass
        await _write_fake_mp3(out_path, title=track.title, artists=track.artists)
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

    def build_cmd(audio_fmt: str, allow_embed: bool = True) -> list[str]:
        parts: list[str] = [
            ytdlp_path,
            "-x", "--audio-format", audio_fmt,
            "--ffmpeg-location", ffmpeg_path,
        ]
        if ytdlp_add_meta:
            parts.append("--add-metadata")
        # Embed YouTube thumbnail when allowed
        if allow_embed and embed_thumb:
            parts.append("--embed-thumbnail")
        # Build ffmpeg post-processor args dynamically per format
        fmt_flags: list[str] = []
        if clean_tags:
            fmt_flags += ["-map_metadata", "-1"]
        if audio_fmt.lower() == "mp3":
            fmt_flags += ["-id3v2_version", "3", "-write_id3v1", "1"]
        # Always set our explicit metadata (artist/title[/album])
        ff_args = " ".join(fmt_flags + pp_args)
        parts.extend(["--ppa", f"ffmpeg:{ff_args}"])
        parts.extend(["-o", str(tmp_out) + ".%(ext)s", cand.url])
        return parts

    cmd = build_cmd(settings.preferred_audio_format, allow_embed=True)
    # Run command blocking (in thread to not block event loop)
    def _run():
        print(f"[downloader] Using yt-dlp={ytdlp_path} ffmpeg={ffmpeg_path}")
        print(f"[downloader] Running: {' '.join(shlex.quote(c) for c in cmd)}")
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError as e:
            raise RuntimeError(f"Executable not found: {e.filename}. Check YT_DLP_BIN/FFMPEG_BIN or PATH.") from e
        except subprocess.CalledProcessError as e:
            # Fallback: if mp3 failed, try m4a without thumbnail embedding (more compatible on minimal ffmpeg)
            pref = settings.preferred_audio_format.lower()
            if pref == "mp3":
                fcmd = build_cmd("m4a", allow_embed=True)
                print("[downloader] mp3 conversion failed; retrying with m4a (no thumbnail embed)")
                print(f"[downloader] Running: {' '.join(shlex.quote(c) for c in fcmd)}")
                subprocess.run(fcmd, check=True)
            else:
                raise
    await asyncio.to_thread(_run)
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
            print(f"[downloader] Renaming {produced} -> {final_path}")
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
    return DownloadOutcome(filepath=out_path, format=fmt, bitrate_kbps=None, filesize_bytes=size, checksum_sha256=checksum)
