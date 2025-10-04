import pytest

from backend.app.utils.normalize import normalize_track


@pytest.mark.parametrize(
    "artists,expected_primary,expected_clean",
    [
        ("Ausmax", "Ausmax", "Ausmax"),
        ("Phoenix", "Phoenix", "Phoenix"),
        ("Artist x Another", "Artist", "Artist & Another"),
        ("Artist   x   Another", "Artist", "Artist & Another"),
        ("Artist × Another", "Artist", "Artist & Another"),
        ("Artist X Another", "Artist", "Artist & Another"),
        ("Artist feat. Someone x Another", "Artist", "Artist & Someone & Another"),
    ],
)
def test_normalize_x_separator(artists, expected_primary, expected_clean):
    n = normalize_track(artists, "Title")
    assert n.primary_artist == expected_primary
    assert n.clean_artists == expected_clean
