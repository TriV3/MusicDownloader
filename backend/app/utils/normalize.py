"""
Utilities for normalizing track metadata.

Responsibilities:
- Normalize artist/title (remove featured markers, version notes, punctuation)
- Extract features (primary artist, clean title, remix/live/remaster flags)
- Duration tolerance helpers for matching

All functions are pure and deterministic.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


_FEATURE_PATTERNS = [
    # remix/edits
    r"\b(extended mix|club mix|original mix|radio edit|edit|remix)\b",
    # live/remaster
    r"\b(live( version)?|remastered?( \d{2,4})?)\b",
]

_FEATURE_RE = re.compile("|".join(_FEATURE_PATTERNS), flags=re.IGNORECASE)

_FEAT_RE = re.compile(
    r"\b(feat\.?|ft\.?|featuring)\b\s*[^()\-·–—]+",
    flags=re.IGNORECASE,
)

_PARENS_CONTENT_RE = re.compile(r"\([^)]*\)")
# Match a trailing dash and any following descriptor (handles -, –, —)
_DASH_SUFFIX_RE = re.compile(r"\s*[\-–—]\s*[^\-–—()]+$")


def _normalize_dash_variants(text: str) -> str:
    """Replace unicode dash variants with a simple ASCII hyphen.

    Also normalizes surrounding spaces to single spaces.
    """
    # Replace en/em dashes with a plain hyphen; keep existing spacing to avoid breaking names like 'Jay-Z'
    text = text.replace("–", "-").replace("—", "-")
    # Collapse remaining whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_artist_separators(artists: str) -> str:
    """Unify common collaboration separators to a canonical form.

    Rules:
    - Map 'x', '×', '+', '/', 'and', 'with' (case-insensitive) to '&'
    - Keep existing ',' and '&' as-is
    - Collapse duplicate separators and extra spaces
    """
    s = artists
    # First normalize dash variants (rare inside artists) and spacing consistently
    s = _normalize_dash_variants(s)
    # Replace various separators with ampersand
    s = re.sub(r"(?i)\s*[x×]\s*", " & ", s)
    s = re.sub(r"\s*\+\s*", " & ", s)
    s = re.sub(r"\s*/\s*", " & ", s)
    s = re.sub(r"(?i)\s*\band\b\s*", " & ", s)
    s = re.sub(r"(?i)\s*\bwith\b\s*", " & ", s)
    # Collapse multiple separators
    s = re.sub(r"\s*&\s*&\s*", " & ", s)
    s = re.sub(r"\s*,\s*,\s*", ", ", s)
    # Normalize spaces around comma and ampersand
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"\s*&\s*", " & ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_accents(text: str) -> str:
    """Remove accents and normalize unicode to NFKD then ASCII-ish."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _clean_punctuation(text: str) -> str:
    # Keep alphanumerics and common separators, collapse spaces
    text = re.sub(r"[^a-zA-Z0-9&,+/\\'\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass(frozen=True)
class NormalizedTrack:
    primary_artist: str
    clean_artists: str
    clean_title: str
    normalized_artists: str
    normalized_title: str
    is_remix_or_edit: bool
    is_live: bool
    is_remaster: bool


def _extract_primary_artist(artists: str) -> str:
    parts = re.split(r"\s*(,|&| x | and )\s*", artists, flags=re.IGNORECASE)
    # parts will include delimiters; take first token
    primary = parts[0] if parts else artists
    return primary.strip()


def normalize_track(artists: str, title: str) -> NormalizedTrack:
    """
    Normalize artists and title removing featured markers and version notes.

    Returns a NormalizedTrack with flags.
    """
    orig_artists = artists or ""
    orig_title = title or ""

    # Replace unicode dash variants and normalize spacing (helps both artists and title)
    orig_artists = _normalize_artist_separators(orig_artists)
    orig_title = _normalize_dash_variants(orig_title)

    # Remove featured mentions from artists and title
    artists_wo_feat = _FEAT_RE.sub("", orig_artists)
    title_wo_feat = _FEAT_RE.sub("", orig_title)

    # Strip bracketed content and dash suffixes that often include version info
    title_base = _PARENS_CONTENT_RE.sub("", title_wo_feat)
    title_base = _DASH_SUFFIX_RE.sub("", title_base)

    # Feature flags from original title (so we do not miss bracketed keywords)
    flags_src = f"{orig_title} {orig_artists}"
    is_remix_or_edit = bool(re.search(r"\b(remix|edit|mix)\b", flags_src, re.IGNORECASE))
    is_live = bool(re.search(r"\blive\b", flags_src, re.IGNORECASE))
    is_remaster = bool(re.search(r"\bremaster(?:ed)?\b", flags_src, re.IGNORECASE))

    # Remove descriptive keywords from cleaned title
    title_base = _FEATURE_RE.sub("", title_base)

    # Strip accents before punctuation cleanup to preserve base letters
    artists_no_accents = _strip_accents(artists_wo_feat)
    title_no_accents = _strip_accents(title_base)

    # Cleanup punctuation/spacing and normalize case
    # Apply separator normalization on the accent-stripped artists once more to ensure symbols survived
    artists_no_accents = _normalize_artist_separators(artists_no_accents)
    clean_artists = _clean_punctuation(artists_no_accents)
    clean_title = _clean_punctuation(title_no_accents)

    # Primary artist
    primary = _extract_primary_artist(clean_artists)

    # Normalized lowercased
    norm_artists = clean_artists.lower()
    norm_title = clean_title.lower()

    return NormalizedTrack(
        primary_artist=primary,
        clean_artists=clean_artists,
        clean_title=clean_title,
        normalized_artists=norm_artists,
        normalized_title=norm_title,
        is_remix_or_edit=is_remix_or_edit,
        is_live=is_live,
        is_remaster=is_remaster,
    )


def durations_close_ms(a_ms: Optional[int], b_ms: Optional[int], tolerance_ms: int = 2000) -> bool:
    """Return True if both durations are present and within tolerance in ms."""
    if a_ms is None or b_ms is None:
        return False
    return abs(a_ms - b_ms) <= max(0, tolerance_ms)


def duration_delta_sec(a_ms: Optional[int], b_ms: Optional[int]) -> Optional[float]:
    """Return absolute delta in seconds if both are present; otherwise None."""
    if a_ms is None or b_ms is None:
        return None
    return abs(a_ms - b_ms) / 1000.0
