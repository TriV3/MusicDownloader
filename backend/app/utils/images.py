from __future__ import annotations

import re
from typing import Optional


_YT_ID_PATTERNS = [
    re.compile(r"(?:v=|/videos/|embed/|youtu\.be/)([A-Za-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"^([A-Za-z0-9_-]+)$"),  # raw id of any length (tests may use short fakes)
]


def extract_youtube_id(url_or_id: str) -> Optional[str]:
    if not url_or_id:
        return None
    for pat in _YT_ID_PATTERNS:
        m = pat.search(url_or_id)
        if m:
            return m.group(1)
    return None


def youtube_thumbnail_url(external_id_or_url: str, prefer_maxres: bool = True) -> Optional[str]:
    """Return a public thumbnail URL for a YouTube video id or URL.

    If prefer_maxres is True, we point to maxresdefault.jpg which may not exist for all videos;
    clients should gracefully fallback. Otherwise, we return hqdefault.jpg which is widely available.
    """
    vid = extract_youtube_id(external_id_or_url)
    if not vid:
        return None
    if prefer_maxres:
        return f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
    return f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
