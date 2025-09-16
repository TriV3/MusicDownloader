from __future__ import annotations

from typing import Optional, Tuple
import mimetypes
import os


def parse_http_range(range_header: Optional[str], file_size: int) -> Optional[Tuple[int, int]]:
    """
    Parse a single HTTP Range header value of the form "bytes=start-end" and return (start, end).
    Supports suffix-byte-range-spec ("bytes=-N") and open-ended ("bytes=N-").
    Returns None if header is missing. Raises ValueError on invalid format or unsatisfiable ranges.
    """
    if not range_header:
        return None

    value = range_header.strip()
    if not value.lower().startswith("bytes="):
        raise ValueError("Unsupported range unit")

    spec = value[6:].strip()
    # Reject multiple ranges for simplicity
    if "," in spec:
        raise ValueError("Multiple ranges not supported")

    if "-" not in spec:
        raise ValueError("Invalid range format")

    start_str, end_str = spec.split("-", 1)
    start_str = start_str.strip()
    end_str = end_str.strip()

    if start_str == "" and end_str == "":
        raise ValueError("Invalid empty range")

    if start_str == "":
        # suffix-byte-range-spec: last N bytes
        try:
            suffix_len = int(end_str)
        except ValueError as e:  # pragma: no cover - defensive
            raise ValueError("Invalid suffix range") from e
        if suffix_len <= 0:
            raise ValueError("Invalid suffix length")
        if suffix_len > file_size:
            start = 0
        else:
            start = file_size - suffix_len
        end = file_size - 1
    else:
        try:
            start = int(start_str)
        except ValueError as e:  # pragma: no cover - defensive
            raise ValueError("Invalid start value") from e
        if start < 0 or start >= file_size:
            raise ValueError("Start out of range")

        if end_str == "":
            # bytes N- (to end)
            end = file_size - 1
        else:
            try:
                end = int(end_str)
            except ValueError as e:  # pragma: no cover - defensive
                raise ValueError("Invalid end value") from e
            if end < start:
                raise ValueError("End before start")
            if end >= file_size:
                # Clamp to last byte
                end = file_size - 1

    return (start, end)


def build_content_range_header(start: int, end: int, total: int) -> str:
    return f"bytes {start}-{end}/{total}"


def pick_audio_mime_from_path(path: str) -> str:
    """
    Return a suitable audio mime for common file extensions.
    Falls back to mimetypes.guess_type.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        return "audio/mpeg"
    if ext in (".m4a", ".mp4", ".aac"):
        return "audio/mp4"
    if ext == ".flac":
        return "audio/flac"
    if ext == ".wav":
        return "audio/wav"
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"
