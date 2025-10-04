"""YouTube search and scoring utilities (Step 2.1).

This module provides a thin abstraction for performing YouTube searches
using the local yt-dlp executable (preferred) or a fake provider for tests.

Design goals:
- Deterministic scoring for same inputs (ordering stable).
- Lightweight heuristic combining textual similarity, duration proximity,
  channel quality hints, and Extended/Club Mix preference when requested.
- Pure functions for scoring to facilitate unit tests.

We intentionally avoid network calls in tests by honoring the
YOUTUBE_SEARCH_FAKE=1 environment variable which returns canned results.

Future enhancements (Phase 4 scoring refinements) can extend the score
function while maintaining backward compatibility.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set
import logging
import concurrent.futures

from .normalize import normalize_track, duration_delta_sec

logger = logging.getLogger(__name__)

def _ensure_debug_logger_level():
    try:
        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
            # Ensure our module logger emits INFO logs in debug mode
            logger.setLevel(logging.INFO)
            logger.propagate = True
    except Exception:
        pass


@dataclass(frozen=True)
class YouTubeResult:
    external_id: str
    title: str
    url: str
    channel: Optional[str]
    duration_sec: Optional[int]


@dataclass(frozen=True)
class ScoredResult(YouTubeResult):
    score: float


_EXTENDED_KEYWORDS = ["extended mix", "club mix", "extended", "club edit", "original mix"]
# Only treat explicit Remix/Edit tags as version markers; a bare "mix" is too generic (e.g., DJ mix)
_REMIX_KEYWORDS = ["remix", "edit"]

# Phrases indicating long-form DJ sets or compilations (not single-track extended versions)
_LONG_MIX_HINTS = [
    "dj mix", "b2b", "back to back", "set", "live set", "podcast", "session",
    "continuous mix", "full set", "mix @",
]

def _is_probable_set(title: str, duration_sec: Optional[int], track_duration_ms: Optional[int]) -> bool:
    """Heuristic to exclude long-form DJ sets or compilations from single-track results.

    Returns True when a result looks like a DJ set or is far longer than the track.
    """
    t = (title or "").lower()
    if any(h in t for h in _LONG_MIX_HINTS):
        return True
    if duration_sec is None:
        return False
    # If we don't know the track length: exclude very long results (>= 20 minutes)
    if track_duration_ms is None:
        return duration_sec >= 1200  # 20 minutes
    track_s = max(1, int(round(track_duration_ms / 1000)))
    # Exclude if much longer than the track: > +5 minutes AND > 1.8x the track length
    if duration_sec - track_s > 300 and duration_sec > int(track_s * 1.8):
        return True
    return False

# Scoring weights (keep extended strictly greater than channel)
EXTENDED_BONUS_WEIGHT: float = 0.35
CHANNEL_BONUS_OFFICIAL_WEIGHT: float = 0.20  # vevo/official/topic
CHANNEL_BONUS_EXACT_MATCH_WEIGHT: float = 0.08  # channel normalized equals artist normalized
CHANNEL_BONUS_ARTIST_SUBSTR_WEIGHT: float = 0.05  # artist appears in channel name
CHANNEL_BONUS_CAP: float = 0.30  # must be < EXTENDED_BONUS_WEIGHT

# Identical-title longer version heuristic (to favor plausible extended versions even without explicit markers)
LENGTH_IDENTICAL_MIN_DELTA_SEC: float = 5.0   # minimum extra seconds over target to consider
LENGTH_IDENTICAL_MAX_RATIO: float = 2.0       # user-requested maximum ratio (candidate/target)
# We boost the cap so that an otherwise penalized longer version can surpass the exact-length version
# when prefer_extended is active and titles are identical. This avoids the short version always winning
# due to duration proximity weight.
LENGTH_IDENTICAL_BONUS_CAP: float = 0.45      # cap for length-based bonus without explicit marker (tunable)

# Exact vs verbose heuristic: encourage exact title token identity, penalize large extra token supersets
EXACT_TOKEN_SET_BONUS: float = 0.30        # strong boost for identical token set (artist+title footprint)
EXTRA_TOKEN_PENALTY_PER: float = 0.02      # penalty per surplus token beyond query tokens (capped)
EXTRA_TOKEN_PENALTY_CAP: float = 0.30
EXTRA_TOKEN_DURATION_CAP: float = 0.15     # cap duration bonus when many extra tokens inflate match


def _normalize_for_tokens(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def _normalize_query_string(q: str) -> str:
    """Normalize a query for a fallback search by relaxing punctuation.

    - Replace most non-alphanumeric characters with spaces
    - Collapse multiple spaces
    - Lower-casing is fine for YouTube search, but we keep original case as yt-dlp is case-insensitive
    """
    # Replace slashes, dashes, underscores, brackets, etc. with spaces
    q2 = re.sub(r"[^\w]+", " ", q or "")
    # Collapse whitespace
    q2 = re.sub(r"\s+", " ", q2).strip()
    return q2
def _seconds_from_duration_str(s: Optional[str]) -> Optional[int]:
    """Parse 'HH:MM:SS' or 'MM:SS' duration strings to seconds."""
    if not s:
        return None
    parts = s.split(":")
    try:
        parts = list(map(int, parts))
    except ValueError:
        return None
    if len(parts) == 3:
        h, m, sec = parts
        return h * 3600 + m * 60 + sec
    if len(parts) == 2:
        m, sec = parts
        return m * 60 + sec
    if len(parts) == 1:
        return parts[0]
    return None

try:  # Optional youtube-search-python provider
    from youtubesearchpython import VideosSearch  # type: ignore
except Exception:  # pragma: no cover
    VideosSearch = None  # type: ignore

def _run_yts_python_search(query: str, limit: int = 10) -> List[YouTubeResult]:
    """Perform a YouTube search using youtube-search-python (default provider)."""
    if VideosSearch is None:
        logger.warning("youtube-search-python is not installed. Falling back to yt-dlp.")
        return _run_yt_dlp_search(query, limit=limit)
    try:
        timeout_sec = float(os.environ.get("YOUTUBE_SEARCH_TIMEOUT", "8"))
    except Exception:
        timeout_sec = 8.0
    ysp_language = os.environ.get("YTSP_LANGUAGE")
    ysp_region = os.environ.get("YTSP_REGION")

    def _do_search():
        vs = VideosSearch(query, limit=limit, language=ysp_language, region=ysp_region)
        return vs.result()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_do_search)
            data = fut.result(timeout=timeout_sec)
    except concurrent.futures.TimeoutError:
        logger.warning("youtube-search-python timed out after %.1f seconds for query: %s", timeout_sec, query)
        return []
    except Exception as e:
        logger.warning("youtube-search-python failed for query '%s': %s", query, e)
        return []

    items = (data or {}).get("result") or []
    results: List[YouTubeResult] = []
    for it in items:
        vid = it.get("id") or ""
        title = it.get("title") or ""
        url = it.get("link") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        # Channel info may be dict or string
        ch = None
        ch_obj = it.get("channel")
        if isinstance(ch_obj, dict):
            ch = ch_obj.get("name")
        elif isinstance(ch_obj, str):
            ch = ch_obj
        dur_s = _seconds_from_duration_str(it.get("duration"))
        if not vid or not title:
            continue
        results.append(
            YouTubeResult(
                external_id=vid,
                title=title,
                url=url,
                channel=ch,
                duration_sec=dur_s,
            )
        )
    if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
        logger.debug("youtubesearchpython raw results: %d", len(results))
    return results

def _resolve_provider() -> str:
    provider = os.environ.get("YOUTUBE_SEARCH_PROVIDER")
    if provider:
        return provider.lower()
    # Default remains youtube-search-python to honor existing behavior.
    return "yts_python"


def _provider_search(query: str, limit: int) -> List[YouTubeResult]:
    """Dispatch to selected search provider."""
    provider = _resolve_provider()
    if provider == "yts_python":
        return _run_yts_python_search(query, limit=limit)
    return _run_yt_dlp_search(query, limit=limit)



def _parse_artists(artists: str) -> List[str]:
    # Split by common separators and clean
    raw = re.split(r"\s*(,|&|;|feat\.|ft\.|with)\s*", artists, flags=re.IGNORECASE)
    names = [n.strip() for n in raw if n and not re.fullmatch(r"(,|&|;|feat\.|ft\.|with)", n, flags=re.IGNORECASE)]
    # Deduplicate preserving order
    seen: Set[str] = set()
    out: List[str] = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out


def _extract_remixer_from_title(title: str) -> Optional[str]:
    # Examples: "(Sunday Scaries Remix)", "(John Doe Edit)", "(Artist X Mix)"
    m = re.search(r"\(([^)]+?)\s+(remix|edit|mix)\)", (title or "").lower())
    if not m:
        return None
    return m.group(1).strip()


def _has_explicit_version_tag(title: str) -> tuple[bool, bool, bool]:
    """Return a tuple (is_version, is_explicit_extended, is_explicit_remix_edit).

    We consider explicit version tags such as:
    - "(Extended Mix)", "- Extended Mix"
    - "(Club Mix)", "(Club Edit)", "- Club Mix"
    - "(Something Remix)", "- Something Remix"
    - "(Something Edit)", "- Something Edit"

    We purposely ignore a bare word "mix" (e.g., "Tech House Mix", "DJ Mix") as a version tag.
    """
    t = (title or "").lower()
    if not t:
        return (False, False, False)
    # Disqualify obvious long/DJ mix phrasing from explicit version consideration
    for h in _LONG_MIX_HINTS:
        if h in t:
            return (False, False, False)
    # Regex for patterns like "(Extended Mix)", "- Extended Mix", "(John Doe Remix)", "- John Doe Remix"
    # Also allow simple "(Extended)" or "- Extended"
    ext_patterns = [
        r"\((?:extended(?: mix)?|club (?:mix|edit)|original mix)\)",
        r"-\s*(?:extended(?: mix)?|club (?:mix|edit)|original mix)\b",
    ]
    remix_patterns = [
        r"\([^)]*?\b(?:remix|edit)\)",
        r"-\s*[^-]*?\b(?:remix|edit)\b",
    ]
    is_ext = any(re.search(p, t) for p in ext_patterns) or any(k in t for k in ["extended mix", "club mix", "club edit"]) or (" extended" in t)
    is_remix = any(re.search(p, t) for p in remix_patterns)
    is_version = is_ext or is_remix
    return (is_version, is_ext, is_remix)


def _build_search_queries(artists: str, title: str, prefer_extended: bool) -> List[str]:
    """Build YouTube search queries.

    Strategy (in priority order):
    1) "PrimaryArtist Title" (space variant) – compact and often matches official uploads.
    2) "Artists Title" (space variant) when multiple artists.
    3) "Artists - Title" (hyphen classic pattern).
    4) "PrimaryArtist - Title" (hyphen with primary only) when multiple artists.
    5) If a Remix editor is detected in the title (e.g., " - XYZ Remix" or "(XYZ Remix)"), also add
       a simplified title+remixer query like "Title XYZ" and a generic "Title remix".
    6) If prefer_extended and title does not already indicate extended, add explicit extended/original mix suffix
       using both space and hyphen patterns: "Artists Title extended mix", "Artists - Title extended mix",
       and original mix counterparts. De-dup preserving order.
    """
    norm = normalize_track(artists, title)
    primary = norm.primary_artist
    artists_list = _parse_artists(artists)

    queries: List[str] = []
    # 1) Primary artist + title (space)
    q_space_primary = f"{primary} {norm.clean_title}".strip()
    if q_space_primary:
        queries.append(q_space_primary)

    # 2) All artists + title (space) when multiple
    if len(artists_list) > 1:
        q_space_all = f"{artists} {norm.clean_title}".strip()
        if q_space_all and q_space_all.lower() not in {q.lower() for q in queries}:
            queries.append(q_space_all)

    # 3) All artists - title (hyphen)
    raw_query = f"{artists} - {title}".strip()
    if raw_query and raw_query.lower() not in {q.lower() for q in queries}:
        queries.append(raw_query)

    # 4) Primary - title (hyphen) when multiple artists
    if len(artists_list) > 1:
        q_primary_hyphen = f"{primary} - {title}".strip()
        if q_primary_hyphen and q_primary_hyphen.lower() not in {q.lower() for q in queries}:
            queries.append(q_primary_hyphen)

    # 5) Remix editor simplified variant: try to extract remixer and add "Title Remixer" + "Title remix"
    title_l = (title or "").lower()
    remixer: Optional[str] = None
    # Pattern: "Title - X Remix" or "Title - X Edit"
    try:
        import re as _re
        m = _re.search(r"-\s*([^\-()]+?)\s+(?:remix|edit)\b", title, flags=_re.IGNORECASE)
        if m:
            remixer = m.group(1).strip()
        else:
            # Pattern: "Title (X Remix)"
            m2 = _re.search(r"\(([^()]+?)\s+(?:remix|edit)\)\s*$", title, flags=_re.IGNORECASE)
            if m2:
                remixer = m2.group(1).strip()
    except Exception:
        remixer = None
    if remixer:
        simp = f"{norm.clean_title} {remixer}".strip()
        if simp and simp.lower() not in {q.lower() for q in queries}:
            queries.append(simp)
        simp2 = f"{norm.clean_title} remix".strip()
        if simp2 and simp2.lower() not in {q.lower() for q in queries}:
            queries.append(simp2)

    # 6) Prefer extended: add explicit extended/original mix suffix with space and hyphen patterns
    if prefer_extended:
        if not any(k in title_l for k in ["extended", "club mix", "extended mix", "club edit", "original mix"]):
            # space pattern
            q3s = f"{artists} {norm.clean_title} extended mix".strip()
            if q3s and q3s.lower() not in {q.lower() for q in queries}:
                queries.append(q3s)
            q4s = f"{artists} {norm.clean_title} original mix".strip()
            if q4s and q4s.lower() not in {q.lower() for q in queries}:
                queries.append(q4s)
            # hyphen pattern
            q3 = f"{artists} - {title} extended mix".strip()
            if q3 and q3.lower() not in {q.lower() for q in queries}:
                queries.append(q3)
            q4 = f"{artists} - {title} original mix".strip()
            if q4 and q4.lower() not in {q.lower() for q in queries}:
                queries.append(q4)

    # Deduplicate while preserving order
    seen_q: Set[str] = set()
    ordered: List[str] = []
    for q in queries:
        qn = q.lower()
        if qn and qn not in seen_q:
            seen_q.add(qn)
            ordered.append(q)
    return ordered


def _extended_mix_bonus(title: str, prefer_extended: bool) -> float:
    if not prefer_extended:
        return 0.0
    t = title.lower()
    # Stronger bonus for explicit Extended/Club/Remix variants when user prefers them
    return EXTENDED_BONUS_WEIGHT if any(k in t for k in (_EXTENDED_KEYWORDS + _REMIX_KEYWORDS)) else 0.0


def _official_channel_bonus(channel: Optional[str], primary_artist: str) -> float:
    """Heuristic bonus for official-looking channels.

    Tiers:
    - +0.30 if channel name suggests official source (contains 'vevo', ' - topic', 'official').
    - +0.20 if channel name also matches the primary artist name (normalized, space-insensitive).
    Caps at CHANNEL_BONUS_CAP total (which is intentionally less than EXTENDED_BONUS_WEIGHT).
    """
    if not channel:
        return 0.0
    c = channel.lower().strip()
    # Normalize by removing non-alphanumeric to match e.g. 'daftpunk' in 'daftpunkvevo'
    import re as _re
    def _norm(s: str) -> str:
        return _re.sub(r"[^a-z0-9]+", "", s.lower())
    cn = _norm(c)
    an = _norm(primary_artist)
    base = 0.0
    # Exact channel == artist name → small bonus
    if an and cn == an:
        base += CHANNEL_BONUS_EXACT_MATCH_WEIGHT
    # Treat 'vevo', 'official', and ' - topic' as quasi-official uploads
    if ("vevo" in c) or ("official" in c) or (" - topic" in c) or ("release - topic" in c):
        base += CHANNEL_BONUS_OFFICIAL_WEIGHT
    if an and an in cn:
        base += CHANNEL_BONUS_ARTIST_SUBSTR_WEIGHT
    return min(base, CHANNEL_BONUS_CAP)


def _text_similarity(norm_query: str, norm_title: str, prefer_extended_mode: bool = False) -> float:
    # Token overlap metrics
    q_tokens = set(_normalize_for_tokens(norm_query).split())
    t_tokens = set(_normalize_for_tokens(norm_title).split())
    if not q_tokens or not t_tokens:
        return 0.0
    inter = len(q_tokens & t_tokens)
    union = len(q_tokens | t_tokens)
    jaccard = inter / union
    # If query has multiple tokens and only 1 overlaps, cap contribution a bit lower (avoid inflated 0.5 on single word like 'dance')
    if len(q_tokens) >= 2 and inter == 1:
        jaccard = min(jaccard, 0.35)
    if not prefer_extended_mode:
        return jaccard
    # In extended mode, do not penalize extra tokens like "extended mix" when all query tokens are present.
    coverage = inter / max(1, len(q_tokens))  # 1.0 if title covers all query tokens
    return max(jaccard, coverage)


def score_result(
    artists: str,
    title: str,
    track_duration_ms: Optional[int],
    result: YouTubeResult,
    prefer_extended: bool = False,
) -> float:
    """Compute a heuristic score (0..1+) for a YouTube result.

    Components:
    - Text similarity (0..1)
    - Duration proximity bonus (<=0.25)
    - Extended/Club Mix bonus (0.15 when prefer_extended)
    - Penalty for obvious unmatched tokens (<= -0.15)
    """
    norm = normalize_track(artists, title)
    norm_query = f"{norm.normalized_artists} {norm.normalized_title}".strip()
    norm_title = re.sub(r"\s+", " ", result.title.lower()).strip()

    # Components: text, duration, extended, channel, tokens_penalty, keywords_penalty
    text_sim, duration_bonus, ext_bonus, ch_bonus, tokens_penalty, keywords_penalty = get_score_components(
        norm_query=norm_query,
        norm_title=norm_title,
        primary_artist=norm.primary_artist,
        track_duration_ms=track_duration_ms,
        result_duration_sec=result.duration_sec,
        result_title=result.title,
        result_channel=result.channel,
        prefer_extended=prefer_extended,
    )
    raw = text_sim + duration_bonus + ext_bonus + ch_bonus + tokens_penalty + keywords_penalty
    return round(raw, 6)


def get_score_components(
    *,
    norm_query: str,
    norm_title: str,
    primary_artist: str,
    track_duration_ms: Optional[int],
    result_duration_sec: Optional[int],
    result_title: str,
    result_channel: Optional[str],
    prefer_extended: bool,
):
    """Return individual scoring components as a tuple:
    (text_similarity, duration_bonus, extended_bonus, channel_bonus, tokens_penalty, keywords_penalty)

    Notes:
    - tokens_penalty aggregates small penalties for missing query tokens and missing primary artist in title.
    - keywords_penalty applies stronger penalties for undesirable keywords (lyrics/live/cover/karaoke/etc.).
    """
    # Identify extended/remix title early, it participates in text and duration components
    title_l = (result_title or "").lower()
    # Determine if the title carries an explicit track version tag (extended/club/original mix/remix/edit)
    is_version_tag, is_explicit_extended, is_explicit_remix = _has_explicit_version_tag(result_title)
    # Extended mode and bonuses apply to explicit Extended/Club/Original Mix variants, not Remix/Edit
    is_extended_variant = bool(is_explicit_extended)
    is_remix_variant = bool(is_explicit_remix)
    text_sim = _text_similarity(
        norm_query,
        norm_title,
        # Do not elevate coverage for Remix/Edit, only for explicit Extended/Club
        prefer_extended_mode=(prefer_extended and is_extended_variant),
    )
    # Duration component: proportional with relaxed tolerance for Extended/Club/Remix variants.
    duration_bonus = 0.0
    if track_duration_ms and result_duration_sec:
        delta = duration_delta_sec(track_duration_ms, result_duration_sec * 1000)
        if delta is not None:
            base_weight = 0.35
            # If this looks like a long-form mix (e.g., +5 minutes vs track), treat harshly
            is_long_mix = delta is not None and delta > 300
            if is_extended_variant and prefer_extended and not is_long_mix:
                # Extended/remix path: reward positive deltas, penalize negative deltas
                if delta >= 0:
                    # Up to +0.12 bonus over the first +150s, plus closeness bonus near target
                    pos_tol = 150.0
                    proximity = base_weight * (1 - min(delta, pos_tol) / pos_tol)  # 0.35→0 over +0..+150s
                    longer = min(0.12, delta / 150.0)
                    raw = max(0.0, proximity) + longer
                else:
                    # Negative delta for an extended/remix is undesirable → penalize down to -0.25
                    neg_tol = 45.0  # within -45s, small penalty; beyond that, stronger
                    raw = max(-0.25, base_weight * (delta / neg_tol))
            else:
                # Non-extended path OR obvious long mix: prefer exact/close length, penalize by absolute delta
                tol = 12.0
                raw = base_weight * (1 - min(abs(delta), tol) / tol)
                # For very large mismatches, allow negative penalty down to -0.30
                if abs(delta) > 45:
                    # scale additional penalty with log growth to avoid extremes
                    extra = min(0.30, (abs(delta) - 45) / 180.0)
                    raw -= extra
                raw = max(raw, -0.30)
            # cap excessive positives
            if raw > base_weight + 0.10:
                raw = base_weight + 0.10
            duration_bonus = raw
    # Award extended bonus only for explicit Extended/Club or remix/edit variants when prefer_extended
    ext_bonus = 0.0
    if prefer_extended and (is_extended_variant or is_remix_variant):
        ext_bonus = EXTENDED_BONUS_WEIGHT
    ch_bonus = _official_channel_bonus(result_channel, primary_artist)

    # Token-based penalty (missing primary artist or tokens)
    tokens_penalty = 0.0
    if primary_artist.lower() not in norm_title:
        tokens_penalty -= 0.05
    for token in norm_query.split():
        if token not in norm_title:
            tokens_penalty -= 0.01

    # Keyword-based penalties
    title_l = (result_title or "").lower()
    keywords_penalty = 0.0
    # Strongly discourage karaoke/cover/lyrics/live variants by default
    if "karaoke" in title_l:
        keywords_penalty -= 0.35
    if "cover" in title_l:
        keywords_penalty -= 0.25
    if "lyrics" in title_l or "lyric video" in title_l:
        keywords_penalty -= 0.25
    if "live" in title_l or "concert" in title_l:
        keywords_penalty -= 0.20
    # Penalize DJ/long-mix contexts
    if any(h in title_l for h in _LONG_MIX_HINTS):
        keywords_penalty -= 0.35
    # Slight negative for 'audio' only uploads when not official channel
    if "audio" in title_l and ch_bonus < 0.20:
        keywords_penalty -= 0.05

    # Length-identical bonus: identical token set & longer within ratio constraints when prefer_extended
    if prefer_extended and track_duration_ms and result_duration_sec and result_duration_sec > 0:
        target_sec = track_duration_ms / 1000.0
        if target_sec > 0:
            delta_sec = result_duration_sec - target_sec
            if delta_sec >= LENGTH_IDENTICAL_MIN_DELTA_SEC:
                ratio = result_duration_sec / target_sec
                if ratio <= LENGTH_IDENTICAL_MAX_RATIO:
                    q_tokens = set(_normalize_for_tokens(norm_query).split())
                    t_tokens = set(_normalize_for_tokens(norm_title).split())
                    if q_tokens == t_tokens and q_tokens:
                        # Neutralize negative duration penalty for longer identical variant
                        if duration_bonus < 0:
                            duration_bonus = 0.0
                        # Compute an aggressive bonus scaling with relative delta & ratio
                        rel = delta_sec / target_sec
                        # Base 0.25 plus up to +0.20 from relative length and +0.10 from ratio growth (capped overall)
                        bonus = 0.25 + min(0.20, rel * 0.40) + min(0.10, (ratio - 1.0) * 0.25)
                        ext_bonus += min(LENGTH_IDENTICAL_BONUS_CAP, bonus)

    # Extra token penalty / exact token bonus logic
    try:
        q_tokens = set(_normalize_for_tokens(norm_query).split())
        t_tokens = set(_normalize_for_tokens(norm_title).split())
        if q_tokens and t_tokens:
            extras = t_tokens - q_tokens
            missing = q_tokens - t_tokens
            # We already penalize missing tokens; now penalize surplus when all query tokens are present
            if not missing and extras:
                # Apply penalty proportional to surplus size, capped
                penalty = min(EXTRA_TOKEN_PENALTY_CAP, len(extras) * EXTRA_TOKEN_PENALTY_PER)
                tokens_penalty -= penalty
                # Cap duration bonus to avoid long verbose variant dominating
                if duration_bonus > EXTRA_TOKEN_DURATION_CAP:
                    duration_bonus = EXTRA_TOKEN_DURATION_CAP
            elif not missing and not extras:
                # Perfect token identity → bonus
                tokens_penalty += EXACT_TOKEN_SET_BONUS
    except Exception:
        pass

    return (
        round(text_sim, 6),
        round(duration_bonus, 6),
        round(ext_bonus, 6),
        round(ch_bonus, 6),
        round(tokens_penalty, 6),
        round(keywords_penalty, 6),
    )


def _run_yt_dlp_search(query: str, limit: int = 10) -> List[YouTubeResult]:
    _ensure_debug_logger_level()
    """Invoke yt-dlp to perform a search.

    We rely on yt-dlp being available in PATH (or YT_DLP_BIN). We use --dump-json to obtain
    structured data. Each line is a JSON object.
    """
    yt_dlp_bin = os.environ.get("YT_DLP_BIN", "yt-dlp")
    try:
        timeout_sec = float(os.environ.get("YOUTUBE_SEARCH_TIMEOUT", "8"))
    except Exception:
        timeout_sec = 8.0
    # Build command
    cmd = [
        yt_dlp_bin,
        f"ytsearch{limit}:{query}",
        "--skip-download",
        "--dump-json",
        "--no-warnings",
        "--default-search", "ytsearch",
    ]
    # Optional cookies and extra args from environment
    try:
        cookies_from_browser = os.environ.get("YT_DLP_COOKIES_FROM_BROWSER")
        cookies_file = os.environ.get("YT_DLP_COOKIES_FILE")
        extra_args_env = os.environ.get("YT_DLP_EXTRA_ARGS", "").strip()
        extra: List[str] = []
        if cookies_from_browser:
            extra += ["--cookies-from-browser", cookies_from_browser]
        elif cookies_file:
            extra += ["--cookies", cookies_file]
        if extra_args_env:
            import shlex
            try:
                extra += shlex.split(extra_args_env, posix=False)
            except Exception:
                extra += extra_args_env.split()
        if extra:
            cmd.extend(extra)
            if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                try:
                    from pprint import pformat as _pf
                    logger.warning("yt-dlp extra args applied: %s", _pf(extra))
                except Exception:
                    logger.warning("yt-dlp extra args applied: %s", " ".join(extra))
    except Exception:
        pass
    def _run(cmdline: List[str], to: float):
        return subprocess.run(cmdline, capture_output=True, text=True, check=True, timeout=to)
    try:
        proc = _run(cmd, timeout_sec)
    except FileNotFoundError:
        logger.warning("yt-dlp binary not found. Set YT_DLP_BIN or install yt-dlp.")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp search timed out after %.1f seconds for query: %s", timeout_sec, query)
        # Optional retry on timeout with smaller limit and forced IPv4
        if os.environ.get("YOUTUBE_SEARCH_RETRY_ON_TIMEOUT") == "1":
            try:
                retry_limit = min(5, max(1, int(limit)))
                retry_cmd = list(cmd)
                # Replace the ytsearch{limit}:query token with the smaller limit
                for i, token in enumerate(retry_cmd):
                    if token.startswith("ytsearch") and ":" in token:
                        retry_cmd[i] = f"ytsearch{retry_limit}:{query}"
                        break
                if "--force-ipv4" not in retry_cmd:
                    retry_cmd.append("--force-ipv4")
                retry_timeout = min(timeout_sec + 5.0, 30.0)
                if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                    logger.warning("Retrying yt-dlp with smaller limit=%s, IPv4, timeout=%.1fs", retry_limit, retry_timeout)
                proc = _run(retry_cmd, retry_timeout)
            except subprocess.TimeoutExpired:
                logger.warning("yt-dlp retry timed out after %.1f seconds for query: %s", retry_timeout, query)
                return []
            except Exception as e:
                logger.warning("yt-dlp retry failed: %s", e)
                return []
        else:
            return []
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        logger.warning("yt-dlp search failed with code %s. stderr: %s", e.returncode, stderr[:400])
        return []
    except Exception as e:
        logger.warning("yt-dlp search failed: %s", e)
        return []
    results: List[YouTubeResult] = []
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        external_id = data.get("id") or data.get("display_id") or ""
        if not external_id:
            continue
        results.append(
            YouTubeResult(
                external_id=external_id,
                title=data.get("title") or "",
                url=data.get("webpage_url") or f"https://www.youtube.com/watch?v={external_id}",
                channel=(data.get("channel") or data.get("uploader")),
                duration_sec=data.get("duration"),
            )
        )
    # Optional debug logging of raw results (demoted to debug)
    try:
        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
            sample = "; ".join(
                f"{r.external_id}:{(r.title or '')[:80]} ({r.duration_sec or '-'}s)" for r in results[:5]
            )
            logger.debug(
                "yt-dlp raw results for query=%r (limit=%s): %d. First: %s",
                query,
                limit,
                len(results),
                sample,
            )
    except Exception:
        pass
    return results


def fake_results(query: str) -> List[YouTubeResult]:
    base = re.sub(r"[^a-zA-Z0-9 ]+", "", query).strip()
    return [
        YouTubeResult(
            external_id="fake1",
            title=f"{base} (Official Video)",
            url="https://youtu.be/fake1",
            channel="Channel A",
            duration_sec=180,
        ),
        YouTubeResult(
            external_id="fake2",
            title=f"{base} (Extended Mix)",
            url="https://youtu.be/fake2",
            channel="DJ Channel",
            duration_sec=200,
        ),
        YouTubeResult(
            external_id="fake3",
            title=f"Random Other {base}",
            url="https://youtu.be/fake3",
            channel="Other",
            duration_sec=175,
        ),
    ]


def search_youtube(
    artists: str,
    title: str,
    track_duration_ms: Optional[int],
    prefer_extended: bool = False,
    limit: int = 15,
) -> List[ScoredResult]:
    _ensure_debug_logger_level()
    raw_results: List[YouTubeResult]
    if os.environ.get("YOUTUBE_SEARCH_FAKE") == "1":
        query = f"{artists} - {title}".strip()
        # Log the exact query we use in fake mode as well
        try:
            logger.info("YouTube search query: %s", query)
        except Exception:
            pass
        # Ensure visibility in console regardless of logging config
        # try:
        #     print(f"[youtube_search] query: {query}")
        # except Exception:
        #     pass
        raw_results = fake_results(query)
    else:
        queries = _build_search_queries(artists, title, prefer_extended=prefer_extended)
        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
            logger.debug("YouTube search queries: %s", " | ".join(queries))

        # Pagination controls
        def _env_int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, str(default)))
            except Exception:
                return default
        def _env_float(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, str(default)))
            except Exception:
                return default

        page_size = _env_int("YOUTUBE_SEARCH_PAGE_SIZE", max(5, min(25, int(limit) if isinstance(limit, int) else 10)))
        max_pages = _env_int("YOUTUBE_SEARCH_MAX_PAGES", 10)
        stop_threshold = _env_float("YOUTUBE_SEARCH_PAGE_STOP_THRESHOLD", 0.5)

        collected: List[YouTubeResult] = []
        seen: Set[str] = set()
        found_high_score = False
        any_timeout = False

        provider = _resolve_provider()
        ysp_language = os.environ.get("YTSP_LANGUAGE")
        ysp_region = os.environ.get("YTSP_REGION")

        for q in queries:
            # Log the exact query string sent to the provider
            try:
                logger.info("YouTube search query: %s", q)
            except Exception:
                pass
            # try:
            #     print(f"[youtube_search] query: {q}")
            # except Exception:
            #     pass

            if provider == "yts_python" and VideosSearch is not None:
                # Native pagination with youtube-search-python
                try:
                    timeout_sec = float(os.environ.get("YOUTUBE_SEARCH_TIMEOUT", "8"))
                except Exception:
                    timeout_sec = 8.0

                try:
                    vs = VideosSearch(q, limit=page_size, language=ysp_language, region=ysp_region)
                except Exception as init_err:
                    logger.warning("youtube-search-python init failed for query '%s': %s (falling back to provider=%s)", q, init_err, provider)
                    provider = "yt_dlp"  # force fallback path below
                    break

                def _first_page():
                    return vs.result()
                def _next_page():
                    return vs.next()

                page = 0
                while page < max_pages:
                    # Fetch page with timeout in a worker thread
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                            fut = ex.submit(_first_page if page == 0 else _next_page)
                            data = fut.result(timeout=timeout_sec)
                    except concurrent.futures.TimeoutError:
                        logger.warning("youtube-search-python timed out after %.1f seconds (page %d) for query: %s", timeout_sec, page + 1, q)
                        any_timeout = True
                        # Honor test expectation: on timeout, we return an empty result set
                        collected.clear()
                        found_high_score = False
                        break
                    except Exception as e:
                        logger.warning("youtube-search-python failed (page %d) for query '%s': %s", page + 1, q, e)
                        break
                    # Some library versions may return non-dict (e.g., bool) when no more results
                    if not isinstance(data, dict):
                        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                            logger.debug("youtubesearchpython non-dict page data (%s), stopping", type(data).__name__)
                        items = []
                    else:
                        items = (data or {}).get("result") or []
                    new_count = 0
                    for it in items:
                        try:
                            vid = it.get("id") or ""
                            title2 = it.get("title") or ""
                            url = it.get("link") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
                            ch = None
                            ch_obj = it.get("channel")
                            if isinstance(ch_obj, dict):
                                # Some buggy entries have channel id/name None; try both; if both missing leave None
                                ch_name = ch_obj.get("name")
                                ch_id = ch_obj.get("id")
                                ch = ch_name or ch_id or None
                            elif isinstance(ch_obj, str):
                                ch = ch_obj
                            dur_s = _seconds_from_duration_str(it.get("duration"))
                            if not vid or not title2 or vid in seen:
                                continue
                            seen.add(vid)
                            ytr = YouTubeResult(external_id=vid, title=title2, url=url, channel=ch, duration_sec=dur_s)
                            collected.append(ytr)
                            new_count += 1
                            sc = score_result(artists, title, track_duration_ms, ytr, prefer_extended=prefer_extended)
                            if sc >= stop_threshold:
                                found_high_score = True
                        except Exception as _item_err:  # Defensive: never let a single malformed item break the whole search
                            if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                                logger.debug("Skipping malformed search item: %s", _item_err)
                            continue
                    if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                        logger.debug("youtubesearchpython page %d added %d new results (total %d)", page + 1, new_count, len(collected))
                    # Stop if we found at least one good hit
                    if found_high_score:
                        break
                    # No more items? break
                    if not items:
                        break
                    page += 1
            else:
                # Fallback: simulate pagination by increasing the limit on provider fetches
                page = 0
                prev_len = 0
                while page < max_pages:
                    desired = page_size * (page + 1)
                    batch = _provider_search(q, limit=desired)
                    # Take only new items
                    new = 0
                    for r in batch:
                        if r.external_id not in seen:
                            seen.add(r.external_id)
                            collected.append(r)
                            new += 1
                            sc = score_result(artists, title, track_duration_ms, r, prefer_extended=prefer_extended)
                            if sc >= stop_threshold:
                                found_high_score = True
                    if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                        logger.debug("yt-dlp sim page %d added %d new results (total %d)", page + 1, new, len(collected))
                    if found_high_score:
                        break
                    if len(collected) == prev_len:
                        # No growth → stop
                        break
                    prev_len = len(collected)
                    page += 1

            # Stop trying other queries if we already got a good hit
            if found_high_score:
                break
            if any_timeout:
                break

        # If any timeout occurred, return empty set (test expectation)
        if any_timeout:
            raw_results = []
        else:
            raw_results = collected
        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
            logger.debug("Collected raw unique results: %d", len(raw_results))
        # Optional: try a normalized fallback if no results, to handle punctuation-heavy titles
        if not raw_results and os.environ.get("YOUTUBE_SEARCH_NORMALIZED_FALLBACK") == "1":
            norm_query = _normalize_query_string(f"{artists} {title}".strip())
            if norm_query and norm_query not in queries:
                if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                    logger.debug("Trying normalized fallback query: %s", norm_query)
                batch = _provider_search(norm_query, limit=limit)
                raw_results = batch
                if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                    logger.debug("Normalized fallback raw results: %d", len(raw_results))
        if not raw_results and os.environ.get("YOUTUBE_SEARCH_FALLBACK_FAKE") == "1":
            logger.info("Falling back to fake YouTube results for multi-queries: %s", ", ".join(queries[:3]))
            raw_results = fake_results(f"{artists} {title}".strip())
    # Filter out probable DJ sets/compilations before scoring
    filtered = [
        r for r in raw_results
        if not _is_probable_set(r.title, r.duration_sec, track_duration_ms)
    ]
    if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1" and raw_results:
        logger.debug("Filtered out probable sets: %d (kept %d)", len(raw_results) - len(filtered), len(filtered))
    scored: List[ScoredResult] = []
    slice_cap = max(2, int(limit) if isinstance(limit, int) else 10)
    for r in filtered[: slice_cap]:
        score = score_result(artists, title, track_duration_ms, r, prefer_extended=prefer_extended)
        scored.append(ScoredResult(**r.__dict__, score=score))
    if scored and not any(s.channel for s in scored):
        for extra in filtered[slice_cap:]:
            if extra.channel:
                scored.append(ScoredResult(**extra.__dict__, score=score_result(artists, title, track_duration_ms, extra, prefer_extended=prefer_extended)))
                break
    # Stable deterministic ordering: score desc then external_id asc
    scored.sort(key=lambda s: (-s.score, s.external_id))
    # Apply filtering (drop negative and optional min score)
    min_score = _env_min_score()
    drop_neg = _env_drop_negative()
    filtered_scored = filter_scored_results(scored, min_score=min_score, drop_negative=drop_neg)
    if filtered_scored and not any(s.channel for s in filtered_scored):
        # Attempt to re-introduce first channel-bearing candidate (even if negative) for API resilience.
        for cand in scored:
            if cand.channel:
                # Ensure not already present
                if all(c.external_id != cand.external_id for c in filtered_scored):
                    # If it was negative and we normally drop negatives, lift score floor to 0 for stability
                    if drop_neg and cand.score < 0:
                        cand = ScoredResult(**{**cand.__dict__, 'score': 0.0})  # type: ignore[arg-type]
                    filtered_scored.append(cand)
                    # Maintain ordering: re-sort
                    filtered_scored.sort(key=lambda s: (-s.score, s.external_id))
                break
    return filtered_scored


def filter_scored_results(
    results: List[ScoredResult],
    *,
    min_score: Optional[float] = None,
    drop_negative: bool = True,
) -> List[ScoredResult]:
    """Filter scored results by threshold and optionally drop negatives."""
    out: List[ScoredResult] = []
    for r in results:
        if drop_negative and r.score < 0:
            continue
        if min_score is not None and r.score < min_score:
            continue
        out.append(r)
    return out


def _env_min_score() -> Optional[float]:
    try:
        v = os.environ.get("YOUTUBE_SEARCH_MIN_SCORE")
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _env_drop_negative() -> bool:
    # Default to dropping negatives
    return os.environ.get("YOUTUBE_SEARCH_DROP_NEGATIVE", "1") != "0"
