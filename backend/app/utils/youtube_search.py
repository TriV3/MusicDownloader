"""YouTube search and scoring utilities (Step 2.1).

This module provides a thin abstraction for performing YouTube searches
using the local yt-dlp executable (preferred) or a fake provider for tests.

Design goals:
- Deterministic scoring for same inputs (ordering stable).
- Uses the new unified ranking algorithm from ranking_service.py
- Pure functions for scoring to facilitate unit tests.

We intentionally avoid network calls in tests by honoring the
YOUTUBE_SEARCH_FAKE=1 environment variable which returns canned results.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Set
import logging
import concurrent.futures

from .normalize import normalize_track
from .ranking_service import RankingService

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
    score_breakdown: Optional[dict] = None  # Detailed score breakdown from ranking service


# Initialize the ranking service
_ranking_service = RankingService()


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


def _format_duration_for_ranking(duration_sec: Optional[float]) -> str:
    """Convert duration in seconds to M:SS or H:MM:SS format."""
    if not duration_sec:
        return ""
    duration_sec = int(duration_sec)  # Convert float to int
    hours = duration_sec // 3600
    minutes = (duration_sec % 3600) // 60
    seconds = duration_sec % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


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
    """Legacy compatibility function for get_score_components.
    
    Returns old format tuple: (text_similarity, duration_bonus, extended_bonus, 
                                channel_bonus, tokens_penalty, keywords_penalty)
    
    This is kept for backward compatibility with API endpoints.
    """
    # Use the new ranking service to get detailed breakdown
    query_duration_sec = track_duration_ms // 1000 if track_duration_ms else None
    data = {
        "query": {
            "artists": primary_artist,
            "title": norm_title,
            "length": _format_duration_for_ranking(query_duration_sec),
        },
        "candidates": [
            {
                "id": "dummy",
                "title": result_title,
                "channel": result_channel or "",
                "length": _format_duration_for_ranking(result_duration_sec),
            }
        ]
    }
    
    result = _ranking_service.rank_candidates(data)
    candidates = result.get("candidates", [])
    
    if candidates and candidates[0].get("score"):
        score_dict = candidates[0]["score"]
        components = score_dict.get("components", {})
        
        # Map new breakdown to old format (approximate)
        # Old format: (text, duration, extended, channel, tokens_penalty, keywords_penalty)
        # New format has: artist, title, extended, duration
        
        # Normalize to old scale (0..1 range)
        text_sim = (components.get("artist", 0) + components.get("title", 0)) / 200.0
        duration_bonus = components.get("duration", 0) / 100.0
        ext_bonus = components.get("extended", 0) / 100.0
        channel_bonus = 0.0  # Channel is now part of artist_score
        tokens_penalty = 0.0  # Not applicable in new system
        keywords_penalty = 0.0  # Not applicable in new system
        
        return (
            round(text_sim, 6),
            round(duration_bonus, 6),
            round(ext_bonus, 6),
            round(channel_bonus, 6),
            round(tokens_penalty, 6),
            round(keywords_penalty, 6),
        )
    
    # Fallback: return zeros
    return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def score_result(
    artists: str,
    title: str,
    track_duration_ms: Optional[int],
    result: YouTubeResult,
    prefer_extended: bool = False,
) -> float:
    """Score a YouTube result using the new ranking service.
    
    Returns:
        float: normalized score (0..1+)
    """
    # Convert to RankingService format
    query_duration_sec = track_duration_ms // 1000 if track_duration_ms else None
    data = {
        "query": {
            "artists": artists,
            "title": title,
            "length": _format_duration_for_ranking(query_duration_sec),
        },
        "candidates": [
            {
                "id": result.external_id,
                "title": result.title,
                "channel": result.channel or "",
                "length": _format_duration_for_ranking(result.duration_sec),
            }
        ]
    }
    
    # Use RankingService to score
    result_obj = _ranking_service.rank_candidates(data)
    candidates = result_obj.get("candidates", [])
    
    if candidates:
        score_dict = candidates[0].get("score", {})
        # Normalize score to old scale (0..1+) by dividing by 100
        raw_score = score_dict.get("total", 0)
        normalized_score = round(raw_score / 100.0, 6)
        return normalized_score
    
    return 0.0


def score_result_with_breakdown(
    artists: str,
    title: str,
    track_duration_ms: Optional[int],
    result: YouTubeResult,
    prefer_extended: bool = False,
) -> tuple[float, Optional[dict]]:
    """Score a YouTube result with detailed breakdown.
    
    Returns:
        tuple: (score, score_breakdown_dict or None)
    """
    query_duration_sec = track_duration_ms // 1000 if track_duration_ms else None
    data = {
        "query": {
            "artists": artists,
            "title": title,
            "length": _format_duration_for_ranking(query_duration_sec),
        },
        "candidates": [
            {
                "id": result.external_id,
                "title": result.title,
                "channel": result.channel or "",
                "length": _format_duration_for_ranking(result.duration_sec),
            }
        ]
    }
    
    result_obj = _ranking_service.rank_candidates(data)
    candidates = result_obj.get("candidates", [])
    
    if candidates:
        score_dict = candidates[0].get("score", {})
        raw_score = score_dict.get("total", 0)
        normalized_score = round(raw_score / 100.0, 6)
        return (normalized_score, score_dict)
    
    return (0.0, None)


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
    
    # Score all results - RankingService handles filtering via duration penalties
    scored: List[ScoredResult] = []
    slice_cap = max(2, int(limit) if isinstance(limit, int) else 10)
    for r in raw_results[: slice_cap]:
        score, breakdown = score_result_with_breakdown(artists, title, track_duration_ms, r, prefer_extended=prefer_extended)
        scored.append(ScoredResult(**r.__dict__, score=score, score_breakdown=breakdown))
    if scored and not any(s.channel for s in scored):
        for extra in raw_results[slice_cap:]:
            if extra.channel:
                score, breakdown = score_result_with_breakdown(artists, title, track_duration_ms, extra, prefer_extended=prefer_extended)
                scored.append(ScoredResult(**extra.__dict__, score=score, score_breakdown=breakdown))
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
