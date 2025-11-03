import math
import pytest
from backend.app.utils.youtube_search import get_score_components, normalize_track


def _score(total_duration_ms, candidate_sec, prefer_extended=True):
    norm = normalize_track("Kapuzen", "Superfly")
    norm_query = f"{norm.normalized_artists} {norm.normalized_title}".strip()
    norm_title = norm_query  # identical title scenario
    comps = get_score_components(
        norm_query=norm_query,
        norm_title=norm_title,
        primary_artist=norm.primary_artist,
        track_duration_ms=total_duration_ms,
        result_duration_sec=candidate_sec,
        result_title="Kapuzen - Superfly",
        result_channel=None,
        prefer_extended=prefer_extended,
    )
    # tuple: (text, duration, extended, channel, tokens_penalty, keywords_penalty)
    return comps


@pytest.mark.skip(reason="Old scoring system - length-identical bonus now handled by implicit extended detection in unified ranking")
def test_longer_identical_gets_bonus():
    base = _score(168000, 168.0)
    longer = _score(168000, 182.0)
    # extended component index 2 should be larger
    assert longer[2] > base[2]


@pytest.mark.skip(reason="Old scoring system - length-identical bonus now handled by implicit extended detection in unified ranking")
def test_ratio_cap_no_bonus_when_too_long():
    excessive = _score(168000, 400.0)  # > 2x ratio ~ 2.38
    base_val = _score(168000, 168.0)[2]
    assert math.isclose(excessive[2], base_val, rel_tol=1e-6)


@pytest.mark.skip(reason="Old scoring system - length-identical bonus now handled by implicit extended detection in unified ranking")
def test_small_delta_no_bonus():
    small = _score(168000, 171.0)
    base = _score(168000, 168.0)
    assert math.isclose(small[2], base[2], rel_tol=1e-6)


@pytest.mark.skip(reason="Old scoring system - length-identical bonus now handled by implicit extended detection in unified ranking")
def test_disabled_without_prefer_extended():
    longer_disabled = _score(168000, 182.0, prefer_extended=False)
    base_disabled = _score(168000, 168.0, prefer_extended=False)
    assert math.isclose(longer_disabled[2], base_disabled[2], rel_tol=1e-6)
