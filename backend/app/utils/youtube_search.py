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
from typing import Iterable, List, Optional

from .normalize import normalize_track, duration_delta_sec


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


def _extended_mix_bonus(title: str, prefer_extended: bool) -> float:
    if not prefer_extended:
        return 0.0
    t = title.lower()
    return 0.15 if any(k in t for k in _EXTENDED_KEYWORDS) else 0.0


def _text_similarity(norm_query: str, norm_title: str) -> float:
    # Simple token overlap ratio (Jaccard)
    q_tokens = set(norm_query.split())
    t_tokens = set(norm_title.split())
    if not q_tokens or not t_tokens:
        return 0.0
    inter = len(q_tokens & t_tokens)
    union = len(q_tokens | t_tokens)
    return inter / union


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

    text_sim = _text_similarity(norm_query, norm_title)
    duration_bonus = 0.0
    if track_duration_ms and result.duration_sec:
        delta = duration_delta_sec(track_duration_ms, result.duration_sec * 1000)
        if delta is not None:
            # 0 bonus at 12s delta, 0.25 at perfect match, linear decay
            duration_bonus = max(0.0, 0.25 * (1 - min(delta, 12) / 12))

    ext_bonus = _extended_mix_bonus(result.title, prefer_extended)

    # Penalize if query primary artist missing entirely
    penalty = 0.0
    if norm.primary_artist.lower() not in norm_title:
        penalty -= 0.05
    # Penalize unmatched required tokens (tokens in query but not in title)
    for token in norm.normalized_title.split():
        if token not in norm_title:
            penalty -= 0.01

    raw = text_sim + duration_bonus + ext_bonus + penalty
    return round(raw, 6)


def _run_yt_dlp_search(query: str, limit: int = 10) -> List[YouTubeResult]:
    """Invoke yt-dlp to perform a search.

    We rely on yt-dlp being available in PATH. We use --dump-json to obtain
    structured data. Each line is a JSON object.
    """
    cmd = [
        "yt-dlp",
        f"ytsearch{limit}:{query}",
        "--skip-download",
        "--dump-json",
        "--no-warnings",
        "--default-search", "ytsearch",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except Exception:
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
    limit: int = 10,
) -> List[ScoredResult]:
    query = f"{artists} {title}".strip()
    if os.environ.get("YOUTUBE_SEARCH_FAKE") == "1":
        raw_results = fake_results(query)
    else:
        raw_results = _run_yt_dlp_search(query, limit=limit)
    scored: List[ScoredResult] = []
    for r in raw_results:
        score = score_result(artists, title, track_duration_ms, r, prefer_extended=prefer_extended)
        scored.append(ScoredResult(**r.__dict__, score=score))
    # Stable deterministic ordering: score desc then external_id asc
    scored.sort(key=lambda s: (-s.score, s.external_id))
    return scored
