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


_EXTENDED_KEYWORDS = ["extended mix", "club mix", "extended", "club edit"]
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
        r"\((?:extended(?: mix)?|club (?:mix|edit))\)",
        r"-\s*(?:extended(?: mix)?|club (?:mix|edit))\b",
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
    """Build search queries prioritizing the exact Spotify name first.

    Strategy:
    1) Exact Spotify artists + title (as-is, including version like "- Radio Edit").
    2) If multiple artists, try primary artist + same title (as-is). This helps when uploads omit featured artists.
    3) If prefer_extended and the title does not already indicate extended, try an explicit "extended mix" suffix with the exact title.

    We intentionally avoid generic "remix" queries, and we don't generate title-only variants.
    """
    norm = normalize_track(artists, title)
    primary = norm.primary_artist
    artists_list = _parse_artists(artists)

    queries: List[str] = []
    # 1) Exact Spotify name (artists + title)
    raw_query = f"{artists} {title}".strip()
    if raw_query:
        queries.append(raw_query)

    # 2) Primary + same title if multiple artists
    if len(artists_list) > 1:
        q2 = f"{primary} {title}".strip()
        if q2 and q2.lower() != raw_query.lower():
            queries.append(q2)

    # 3) Prefer extended: add explicit extended mix suffix to the exact title
    if prefer_extended:
        title_l = (title or "").lower()
        if not any(k in title_l for k in ["extended", "club mix", "extended mix", "club edit"]):
            q3 = f"{artists} {title} extended mix".strip()
            if q3 and q3.lower() not in {q.lower() for q in queries}:
                queries.append(q3)

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
    return 0.35 if any(k in t for k in (_EXTENDED_KEYWORDS + _REMIX_KEYWORDS)) else 0.0


def _official_channel_bonus(channel: Optional[str], primary_artist: str) -> float:
    """Heuristic bonus for official-looking channels.

    Tiers:
    - +0.30 if channel name suggests official source (contains 'vevo', ' - topic', 'official').
    - +0.20 if channel name also matches the primary artist name (normalized, space-insensitive).
    Caps at +0.50 total.
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
    # Exact channel == artist name → treat as official source
    if an and cn == an:
        base += 0.30
    # Treat ' - Topic' and 'Release - Topic' as quasi-official uploads
    if ("vevo" in c) or ("official" in c) or (" - topic" in c) or ("release - topic" in c):
        base += 0.30
    if an and an in cn:
        base += 0.20
    return min(base, 0.50)


def _text_similarity(norm_query: str, norm_title: str, prefer_extended_mode: bool = False) -> float:
    # Token overlap metrics
    q_tokens = set(_normalize_for_tokens(norm_query).split())
    t_tokens = set(_normalize_for_tokens(norm_title).split())
    if not q_tokens or not t_tokens:
        return 0.0
    inter = len(q_tokens & t_tokens)
    union = len(q_tokens | t_tokens)
    jaccard = inter / union
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
    # Determine if the title carries an explicit track version tag (extended/club/remix/edit)
    is_version_tag, is_explicit_extended, is_explicit_remix = _has_explicit_version_tag(result_title)
    # Treat as extended variant only when explicit (ignore generic "mix") and not a long-form set
    is_extended_title = is_version_tag and (is_explicit_extended or is_explicit_remix)
    text_sim = _text_similarity(norm_query, norm_title, prefer_extended_mode=(prefer_extended and is_extended_title))
    # Duration component: proportional with relaxed tolerance for Extended/Club/Remix variants.
    duration_bonus = 0.0
    if track_duration_ms and result_duration_sec:
        delta = duration_delta_sec(track_duration_ms, result_duration_sec * 1000)
        if delta is not None:
            base_weight = 0.35
            # If this looks like a long-form mix (e.g., +5 minutes vs track), treat harshly
            is_long_mix = delta is not None and delta > 300
            if is_extended_title and prefer_extended and not is_long_mix:
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
    # Award extended bonus only for explicit extended/remix versions (not generic DJ mixes)
    ext_bonus = 0.0
    if prefer_extended and is_extended_title:
        ext_bonus = 0.35
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
    # Optional debug logging of raw results
    try:
        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
            sample = "; ".join(
                f"{r.external_id}:{(r.title or '')[:80]} ({r.duration_sec or '-'}s)" for r in results[:5]
            )
            # Use warning level so it shows even if root handler is WARNING
            logger.warning(
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
        query = f"{artists} {title}".strip()
        raw_results = fake_results(query)
    else:
        queries = _build_search_queries(artists, title, prefer_extended=prefer_extended)
        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
            logger.warning("YouTube search queries: %s", " | ".join(queries))
        collected: List[YouTubeResult] = []
        seen: Set[str] = set()
        for q in queries:
            batch = _run_yt_dlp_search(q, limit=limit)
            for r in batch:
                if r.external_id not in seen:
                    seen.add(r.external_id)
                    collected.append(r)
            if len(collected) >= limit:
                break
        raw_results = collected
        if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
            logger.warning("Collected raw unique results: %d", len(raw_results))
        # Optional: try a normalized fallback if no results, to handle punctuation-heavy titles
        if not raw_results and os.environ.get("YOUTUBE_SEARCH_NORMALIZED_FALLBACK") == "1":
            norm_query = _normalize_query_string(f"{artists} {title}".strip())
            if norm_query and norm_query not in queries:
                if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                    logger.warning("Trying normalized fallback query: %s", norm_query)
                batch = _run_yt_dlp_search(norm_query, limit=limit)
                raw_results = batch
                if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1":
                    logger.warning("Normalized fallback raw results: %d", len(raw_results))
        if not raw_results and os.environ.get("YOUTUBE_SEARCH_FALLBACK_FAKE") == "1":
            logger.info("Falling back to fake YouTube results for multi-queries: %s", ", ".join(queries[:3]))
            raw_results = fake_results(f"{artists} {title}".strip())
    # Filter out probable DJ sets/compilations before scoring
    filtered = [
        r for r in raw_results
        if not _is_probable_set(r.title, r.duration_sec, track_duration_ms)
    ]
    if os.environ.get("YOUTUBE_SEARCH_DEBUG") == "1" and raw_results:
        logger.warning("Filtered out probable sets: %d (kept %d)", len(raw_results) - len(filtered), len(filtered))
    scored: List[ScoredResult] = []
    for r in filtered[: max(1, int(limit) if isinstance(limit, int) else 10)]:
        score = score_result(artists, title, track_duration_ms, r, prefer_extended=prefer_extended)
        scored.append(ScoredResult(**r.__dict__, score=score))
    # Stable deterministic ordering: score desc then external_id asc
    scored.sort(key=lambda s: (-s.score, s.external_id))
    return scored
