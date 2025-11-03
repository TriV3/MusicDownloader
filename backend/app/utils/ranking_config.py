"""
Configuration parameters for the YouTube search ranking algorithm.
All bonuses, penalties, and thresholds are defined here for easy tuning.
"""


class RankingConfig:
    """Configuration for the search ranking algorithm."""
    
    # Artist Score Parameters
    ARTIST_BONUS_PER_MATCH = 50
    ARTIST_BONUS_PER_FUZZY_MATCH = 35  # Lower bonus for fuzzy match (e.g., "Marten Horger" matches "Marten Hørger")
    ARTIST_PENALTY_PER_MISS = -15  # Reduced penalty to not over-penalize partial artist matches
    ARTIST_CHANNEL_EXACT_MATCH_BONUS = 95  # Bonus when channel name matches artist exactly (official channel)
    
    # Title Score Parameters
    TITLE_EXACT_MATCH_BONUS = 100
    TITLE_TOKEN_BONUS_PER_MATCH = 15
    TITLE_TOKEN_PENALTY_PER_MISS = -10
    TITLE_REMAINING_TOKEN_PENALTY = -5
    TITLE_REMAINING_TOKEN_PENALTY_MAX = -30
    
    # Extended (Version) Parameters
    EXTENDED_KEYWORDS = {"extended", "club", "original mix"}
    EXTENDED_LARGE_BONUS = 55  # Strong bonus to favor extended versions
    EXTENDED_MAX_REMAINING_PENALTY_ALLOWED = 25  # More lenient to allow for extra tokens in extended titles
    EXTENDED_MIN_ARTIST_SCORE = 30  # At least one good artist match required
    EXTENDED_MIN_TITLE_SCORE = 70  # Title must match well
    EXTENDED_DURATION_BONUS = 10  # Additional bonus for extended versions that are appropriately long
    
    # Duration Score Parameters
    DURATION_PENALTY_TOO_SHORT = -100
    DURATION_MAX_RATIO = 2.0
    DURATION_BONUS_RANGE = {
        "min_bonus": 0,
        "max_bonus": 30,
        "bonus_per_second": 0.5
    }
    
    # Official channel suffixes to strip when matching artist names
    OFFICIAL_CHANNEL_SUFFIXES = [
        " - topic",
        " - official",
        "vevo",
        " official",
        " - audio",
        " music"
    ]
