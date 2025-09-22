import os
from typing import List

import pytest

try:
    from backend.app.utils.youtube_search import ScoredResult, filter_scored_results
except Exception:  # pragma: no cover
    from app.utils.youtube_search import ScoredResult, filter_scored_results


def _sr(score: float) -> ScoredResult:
    return ScoredResult(
        external_id=f"id_{score}",
        title=f"title_{score}",
        url="https://youtu.be/x",
        channel=None,
        duration_sec=None,
        score=score,
    )


def test_filter_drops_negative_by_default():
    items: List[ScoredResult] = [_sr(-0.3), _sr(0.0), _sr(0.12)]
    out = filter_scored_results(items, min_score=None, drop_negative=True)
    assert all(r.score >= 0 for r in out)
    assert [r.score for r in out] == [0.0, 0.12]


def test_filter_min_score_applies_threshold():
    items: List[ScoredResult] = [_sr(-0.1), _sr(0.05), _sr(0.2), _sr(0.6)]
    out = filter_scored_results(items, min_score=0.2, drop_negative=True)
    assert [r.score for r in out] == [0.2, 0.6]
