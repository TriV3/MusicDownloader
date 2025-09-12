import pytest

try:
    from backend.app.utils.normalize import normalize_track, durations_close_ms, duration_delta_sec
except Exception:
    from app.utils.normalize import normalize_track, durations_close_ms, duration_delta_sec


def test_normalize_basic_feat_and_parens():
    n = normalize_track("Artist feat. Guest", "Title (Remastered 2012) - Radio Edit")
    assert n.primary_artist == "Artist"
    assert n.is_remaster is True
    assert n.is_remix_or_edit is True
    assert n.clean_title.lower() == "title"
    assert n.normalized_artists == "artist"
    assert n.normalized_title == "title"


def test_normalize_live_mix_accents_and_delimiters():
    n = normalize_track("Beyoncé & Jay-Z", "Halo - Live at Wembley (Extended Mix)")
    assert n.primary_artist.lower() == "beyonce"  # accent stripped
    assert n.is_live is True
    assert n.is_remix_or_edit is True
    assert n.clean_title.lower() == "halo"
    assert n.normalized_artists == "beyonce & jay-z"


def test_duration_helpers():
    assert durations_close_ms(180000, 181500, tolerance_ms=2000) is True
    assert durations_close_ms(180000, 184000, tolerance_ms=2000) is False
    assert durations_close_ms(None, 1000) is False
    assert duration_delta_sec(2000, 1500) == 0.5
    assert duration_delta_sec(None, 1500) is None
