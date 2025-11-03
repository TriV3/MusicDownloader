# YouTube Search Ranking — Single Model Specification

This document defines the single, unified ranking rules to implement next. It starts from scratch and makes every bonus/penalty configurable.

Goal: sort YouTube results by total score (highest first), prioritizing artist and title matches, then version and duration.

## Normalization
- Lowercase all text.
- Ignore punctuation/separators except those that are part of the reference strings (e.g., keep '&' when it belongs to the actual artist or title like "Block & Crown").
- Tokenize on whitespace after normalization. Keep letters/digits/space and symbols explicitly present in reference strings.

## Score composition
We split the total score into four independent families and sum them:
- Artist Score
- Title Score
- Extended (Version) Score
- Duration Score

Each family is made up of sub-rules with bonuses/penalties. All values below must be configurable (single place to change them).

### Parameters (example knobs)
- Artist
  - ARTIST_BONUS_PER_MATCH
  - ARTIST_PENALTY_PER_MISS
- Title
  - TITLE_EXACT_MATCH_BONUS
  - TITLE_TOKEN_BONUS_PER_MATCH
  - TITLE_TOKEN_PENALTY_PER_MISS
  - TITLE_REMAINING_TOKEN_PENALTY
  - TITLE_REMAINING_TOKEN_PENALTY_MAX (cap)
- Extended (version)
  - EXTENDED_KEYWORDS = {"extended", "club", "original mix"}
  - EXTENDED_LARGE_BONUS
  - EXTENDED_MAX_REMAINING_PENALTY_ALLOWED (threshold)
  - EXTENDED_MIN_ARTIST_SCORE (threshold)
  - EXTENDED_MIN_TITLE_SCORE (threshold)
- Duration
  - DURATION_PENALTY_TOO_SHORT (strong penalty)
  - DURATION_MAX_RATIO = 2.0 (upper ratio limit)
  - DURATION_BONUS_RANGE (proportional bonus mapping for positive deltas)

All parameters MUST be easy to tweak without touching the algorithmic code.

  ## Score breakdown (for frontend/debugging)
  - The implementation MUST record every applied rule with its numeric contribution for each candidate so the UI can display an exact breakdown.
  - Suggested breakdown structure per candidate result:
    - total: number
    - components:
      - artist: number
      - title: number
      - extended: number
      - duration: number
    - details: array of { key: string, value: number, family: "artist"|"title"|"extended"|"duration", note?: string }
  - Examples of keys: "artist.match:Block & Crown", "artist.miss:ArtistName", "title.exact", "title.token:love", "title.miss:party", "title.remaining-token:official", "extended.detected:original mix", "duration.bonus:+12s", "duration.too-short:-8s".

## Scoring algorithm

1) Artist Score
   - For each artist (use the full artist string, e.g., "Block & Crown"), look for its presence in the video title OR in the channel name.
   - If found: +ARTIST_BONUS_PER_MATCH.
   - If not found: −ARTIST_PENALTY_PER_MISS.
   - When an artist is found, remove that exact text from a working copy of the video title so it doesn't count as extra noise later.
   - **Note:** When matching against the channel name, official channel suffixes (e.g., " - Topic", " - Official", "VEVO") should be stripped before comparison to avoid penalizing legitimate artist channels. For example, "AUSMAX - Topic" should match "AUSMAX" without penalty.

2) Title Score
   - First attempt exact title match against the working copy of the video title. If exact, +TITLE_EXACT_MATCH_BONUS and remove that substring from the working title.
   - Otherwise, split the reference title into tokens (preserving symbols like '&' if they are part of the title) and:
     - add +TITLE_TOKEN_BONUS_PER_MATCH for each token found in the working title (and remove that token from the working title),
     - add −TITLE_TOKEN_PENALTY_PER_MISS for each missing token.
   - For every remaining token in the working title (after removing matched artist and title tokens), add a penalty −TITLE_REMAINING_TOKEN_PENALTY per token.
     - Exception: if the token belongs to a detected version mention (see Extended rule), do not penalize it here.
     - Cap the total remaining-token penalty by TITLE_REMAINING_TOKEN_PENALTY_MAX.

3) Extended (version) Bonus
   - Detect an "Extended/Club/Original Mix" version via EXTENDED_KEYWORDS on the working title.
   - Grant EXTENDED_LARGE_BONUS ONLY if ALL are true:
     - absolute value of the remaining-token penalty is ≤ EXTENDED_MAX_REMAINING_PENALTY_ALLOWED, AND
     - Artist Score ≥ EXTENDED_MIN_ARTIST_SCORE, AND
     - Title Score ≥ EXTENDED_MIN_TITLE_SCORE.

4) Duration Score
   - Compare candidate duration (seconds) to target duration.
   - If candidate is shorter than target: apply strong penalty −DURATION_PENALTY_TOO_SHORT.
   - If equal: 0 bonus.
   - If longer but ≤ DURATION_MAX_RATIO × target: add a proportional bonus based on the surplus using DURATION_BONUS_RANGE.
   - Beyond DURATION_MAX_RATIO: no additional bonus (optionally ignore the candidate or keep the score as-is).

5) Aggregation and sorting
   - Final score = Artist Score + Title Score + Extended Bonus + Duration Score.
   - Sort candidates by final score descending.
   - **Tie-breaking:** In case of equal scores, preserve the original order from the search results (i.e., take the first candidate in the list). This ensures stable and predictable ranking.

## Implementation details
- Matching operates on normalized lowercase text.
- Separators/punctuation are ignored except when they are significant characters in the reference strings (e.g., '&' in "Block & Crown").
- The "working copy" removals don’t mutate original values; they prevent double counting across artist, title, and remaining tokens.
- All constants (bonuses/penalties/thresholds) must live in one place (settings or a small config file) for easy tuning.

## Optional complementary rules
- Penalty for words such as "karaoke", "cover", "lyrics", "live" if you want to demote them instead of rejecting. Values must be configurable.
- Progressive penalty for very long tails of remaining tokens (with a cap).
- Small bonus if the channel name exactly matches the artist (configurable). Only enable if a minimal trust signal is desired.
- Hard cap so that candidates containing alien artists cannot exceed a clean identity’s score (configurable cap).

## Test dataset and validation
- The JSON file at docs/search_ranking_cases.json contains queries (reference) + candidates and the expected winner for each case.
- A test reads this JSON, applies the algorithm, and asserts that the top-ranked item equals the expected winner.
- This keeps the ranking stable and auditable when tuning parameters.
