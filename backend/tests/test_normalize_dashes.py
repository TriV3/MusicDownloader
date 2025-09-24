import pytest

try:
    from backend.app.utils.normalize import normalize_track
except Exception:
    from app.utils.normalize import normalize_track


def test_normalize_replaces_em_dash_and_separators():
    n = normalize_track("Tchami, NIIKO X SWAE", "Waiting — Original Mix")
    # No em-dash should remain, normalized_title should use ascii only
    assert "—" not in n.normalized_title
    assert n.normalized_title.startswith("waiting")
    # Artist separators: X should be normalized to '&'
    assert "x" not in n.normalized_artists
    assert "×" not in n.normalized_artists
    assert " & " in n.normalized_artists or "," in n.normalized_artists
