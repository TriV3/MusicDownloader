# YouTube Search Ranking Implementation

## Overview

This implementation follows the specification in `search_ranking.md` and provides a single, unified ranking algorithm for YouTube search results.

## Architecture

The ranking system consists of three main components:

### 1. Configuration (`backend/app/utils/ranking_config.py`)

Contains all tunable parameters for the ranking algorithm:

- **Artist Scoring**: Bonuses for matching artists, penalties for misses
- **Title Scoring**: Bonuses for exact/token matches, penalties for misses and remaining tokens
- **Extended Version Detection**: Keywords, bonuses, and threshold conditions
- **Duration Scoring**: Penalties for short videos, bonuses for appropriate lengths

All parameters are defined in the `RankingConfig` class and can be easily adjusted without modifying the algorithm logic.

### 2. Ranking Service (`backend/app/utils/ranking_service.py`)

The core algorithm implementation with the following key methods:

- `rank_candidates(data)`: Main entry point that takes a query and candidates, returns ranked results with scores
- `score_candidate(query, candidate)`: Scores a single candidate against the query
- `score_artist()`: Artist matching logic
- `score_title()`: Title matching logic
- `score_extended()`: Extended version detection and bonus
- `score_duration()`: Duration comparison scoring

### 3. Tests (`backend/tests/test_ranking_service.py`)

Comprehensive test suite that:

- Validates all test cases from `docs/search_ranking_cases.json`
- Ensures the expected winner has the highest score for each case
- Verifies the score breakdown structure
- Tests individual components (normalization, duration parsing, etc.)

## Scoring Process

The algorithm follows these steps for each candidate:

1. **Normalize** all text (lowercase)
2. **Score Artists**: Check if each artist appears in title or channel name
3. **Score Title**: Look for exact match or individual tokens
4. **Detect Extended Version**: Check for extended/club/original mix keywords
5. **Score Remaining Tokens**: Penalize unexpected words (except extended keywords)
6. **Score Duration**: Compare candidate duration to query duration
7. **Aggregate**: Sum all component scores to get total score
8. **Sort**: Order candidates by total score (descending), preserve original order for ties

## Score Breakdown

Each candidate receives a detailed score breakdown:

```json
{
  "total": 145.5,
  "components": {
    "artist": 50.0,
    "title": 75.5,
    "extended": 40.0,
    "duration": -20.0
  },
  "details": [
    {
      "key": "artist.match:Block & Crown",
      "value": 50,
      "family": "artist",
      "note": "Found in title"
    },
    {
      "key": "title.token:lonely",
      "value": 15,
      "family": "title"
    }
  ]
}
```

This breakdown enables:
- Debugging why a candidate received its score
- UI display showing score composition
- Parameter tuning by analyzing which rules fire most often

## Usage

### Basic Usage

```python
from backend.app.utils.ranking_service import RankingService

service = RankingService()

data = {
    "query": {
        "artists": "Block & Crown",
        "title": "Lonely Heart",
        "length": "4:00"
    },
    "candidates": [
        {
            "id": "c1",
            "channel": "FOXsound Official",
            "title": "Block & Crown - Lonely Heart",
            "length": "5:24"
        },
        {
            "id": "c2",
            "channel": "Da Kastro",
            "title": "Lonely Heart (Original Mix)",
            "length": "7:47"
        }
    ]
}

result = service.rank_candidates(data)

for candidate in result['candidates']:
    print(f"{candidate['id']}: {candidate['score']['total']}")
    print(f"  {candidate['title']}")
```

### Custom Configuration

```python
from backend.app.utils.ranking_service import RankingService
from backend.app.utils.ranking_config import RankingConfig

config = RankingConfig()
config.ARTIST_BONUS_PER_MATCH = 60
config.EXTENDED_LARGE_BONUS = 50

service = RankingService(config)
result = service.rank_candidates(data)
```

## Testing

Run the test suite:

```bash
# From project root
python -m pytest backend/tests/test_ranking_service.py -v

# Or using the VS Code task: "Test Ranking Algorithm"
```

Or use the VS Code task (see `.vscode/tasks.json`).

## Tuning Parameters

To improve ranking results:

1. Run tests to identify failing cases
2. Examine score breakdowns for those cases
3. Adjust parameters in `ranking_config.py`
4. Re-run tests to validate improvements
5. Iterate until all test cases pass

Common adjustments:
- Increase `ARTIST_BONUS_PER_MATCH` if artist presence is undervalued
- Adjust `EXTENDED_MIN_*_SCORE` thresholds to make extended bonus stricter/looser
- Modify `DURATION_BONUS_RANGE` to emphasize or de-emphasize duration matching
- Change `TITLE_REMAINING_TOKEN_PENALTY` to be more/less forgiving of extra words

## Configuration Parameters Reference

### Artist Score
- `ARTIST_BONUS_PER_MATCH` (default: 50): Points awarded when an artist is found in title or channel
- `ARTIST_PENALTY_PER_MISS` (default: -20): Points deducted when an artist is not found

### Title Score
- `TITLE_EXACT_MATCH_BONUS` (default: 100): Large bonus for exact title match
- `TITLE_TOKEN_BONUS_PER_MATCH` (default: 15): Points per matching title token
- `TITLE_TOKEN_PENALTY_PER_MISS` (default: -10): Penalty per missing title token
- `TITLE_REMAINING_TOKEN_PENALTY` (default: -5): Penalty per extra token in video title
- `TITLE_REMAINING_TOKEN_PENALTY_MAX` (default: -30): Maximum total penalty for extra tokens

### Extended Version
- `EXTENDED_KEYWORDS` (default: {"extended", "club", "original mix"}): Keywords to detect extended versions
- `EXTENDED_LARGE_BONUS` (default: 40): Bonus for extended versions that meet quality thresholds
- `EXTENDED_MAX_REMAINING_PENALTY_ALLOWED` (default: 15): Max remaining penalty to still award extended bonus
- `EXTENDED_MIN_ARTIST_SCORE` (default: 30): Minimum artist score required for extended bonus
- `EXTENDED_MIN_TITLE_SCORE` (default: 50): Minimum title score required for extended bonus

### Duration Score
- `DURATION_PENALTY_TOO_SHORT` (default: -100): Strong penalty when candidate is shorter than query
- `DURATION_MAX_RATIO` (default: 2.0): Maximum acceptable ratio (candidate/query duration)
- `DURATION_BONUS_RANGE`: Configuration for proportional bonus on longer durations
  - `min_bonus` (default: 0): Starting bonus
  - `max_bonus` (default: 30): Maximum bonus cap
  - `bonus_per_second` (default: 0.5): Bonus rate per extra second

### Channel Matching
- `OFFICIAL_CHANNEL_SUFFIXES`: List of suffixes to strip when matching channel to artist
  - Default: [" - topic", " - official", "vevo", " official", " - audio", " music"]

## Example Scoring Scenarios

### Scenario 1: Perfect Match
**Query**: "Block & Crown - Lonely Heart" (4:00)
**Candidate**: "Block & Crown - Lonely Heart" on "Block & Crown - Topic" (4:00)

- Artist: +50 (found in title)
- Title: +100 (exact match)
- Extended: 0 (no extended keywords)
- Duration: 0 (exact match)
- **Total: 150**

### Scenario 2: Extended Version
**Query**: "AUSMAX - Love" (2:39)
**Candidate**: "AUSMAX - Love (Extended Mix)" on "FOXsound Official" (5:24)

- Artist: +50 (found in title)
- Title: +30 (2 tokens match: love, ausmax)
- Remaining: -10 (for "mix")
- Extended: +40 (conditions met)
- Duration: +15 (longer but within range)
- **Total: 125**

### Scenario 3: Wrong Artist
**Query**: "Block & Crown - Lonely Heart" (4:00)
**Candidate**: "Other Artist - Lonely Heart" (4:00)

- Artist: -20 (Block & Crown not found)
- Title: +15 (partial match on "lonely heart")
- Extended: 0
- Duration: 0
- **Total: -5**

## Integration with Existing Code

To integrate this new ranking system into your existing YouTube search flow:

1. Import the ranking service in `youtube_search.py`
2. Replace calls to `score_result()` with the new `RankingService`
3. Update the data structure to match the expected input/output format
4. Remove the old scoring functions

See the implementation in `youtube_search.py` for the complete integration.

## Future Enhancements

Possible additions (per specification):
- Penalty for "karaoke", "cover", "lyrics", "live" keywords (configurable)
- Progressive penalty for very long titles (with a cap)
- Channel name exact match bonus (configurable)
- Hard cap preventing alien artist results from ranking too high

## Troubleshooting

### Tests Failing

1. Check the failed case output to see expected vs actual winner
2. Examine the score breakdown in test output
3. Adjust parameters in `ranking_config.py`
4. Re-run tests

### Unexpected Rankings

1. Use the ranking service directly with debug output
2. Examine the score breakdown for each candidate
3. Identify which component is causing the issue
4. Adjust the relevant parameters

### Performance Issues

The ranking algorithm is designed to be fast:
- O(n) complexity for n candidates
- No network calls
- Pure functions for easy testing and caching
