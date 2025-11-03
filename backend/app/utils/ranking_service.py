"""
YouTube search ranking service.
Implements the single unified ranking algorithm as specified in docs/search_ranking.md
"""

import re
from typing import Dict, List, Any, Set, Tuple

from .ranking_config import RankingConfig


class ScoreBreakdown:
    """Detailed breakdown of a candidate's score."""
    
    def __init__(self):
        self.total = 0.0
        self.components = {
            "artist": 0.0,
            "title": 0.0,
            "extended": 0.0,
            "duration": 0.0
        }
        self.details: List[Dict[str, Any]] = []
    
    def add_detail(self, key: str, value: float, family: str, note: str = None):
        """Add a scoring detail."""
        detail = {
            "key": key,
            "value": value,
            "family": family
        }
        if note:
            detail["note"] = note
        self.details.append(detail)
        self.components[family] += value
        self.total += value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total": round(self.total, 2),
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "details": self.details
        }


class RankingService:
    """Service to rank YouTube search results based on query criteria."""
    
    def __init__(self, config: RankingConfig = None):
        self.config = config or RankingConfig()
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text by converting to lowercase.
        Keep significant characters like '&' and special characters (ø, é, etc.) 
        as they may be part of artist/title names.
        """
        return text.lower()
    
    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into words.
        Preserves symbols like '&' when they appear as standalone tokens.
        """
        tokens = re.findall(r'\S+', text)
        return [self.normalize_text(t) for t in tokens]
    
    def strip_official_suffixes(self, channel: str) -> str:
        """Remove official channel suffixes from channel name."""
        normalized = self.normalize_text(channel)
        for suffix in self.config.OFFICIAL_CHANNEL_SUFFIXES:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
        return normalized
    
    def normalize_for_fuzzy_match(self, text: str) -> str:
        """
        Normalize text for fuzzy matching (used for fallback comparisons).
        Removes special characters for more lenient matching.
        """
        import unicodedata
        # Convert to lowercase
        text = text.lower()
        # Normalize Unicode characters (e.g., ø -> o, é -> e)
        text = unicodedata.normalize('NFKD', text)
        # Remove combining characters (accents, etc.)
        text = ''.join([c for c in text if not unicodedata.combining(c)])
        # Additional manual replacements for characters that don't decompose well
        replacements = {
            'ø': 'o',
            'æ': 'ae',
            'œ': 'oe',
            'ß': 'ss',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    
    def parse_duration(self, duration_str: str) -> int:
        """Parse duration string (M:SS or H:MM:SS) to seconds."""
        if not duration_str:
            return 0
        parts = duration_str.split(':')
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return 0
    
    def find_and_remove(self, text: str, pattern: str) -> Tuple[bool, str]:
        """
        Find pattern in text (case-insensitive) and remove it if found.
        Returns (found, remaining_text).
        """
        normalized_text = self.normalize_text(text)
        normalized_pattern = self.normalize_text(pattern)
        
        if normalized_pattern in normalized_text:
            idx = normalized_text.find(normalized_pattern)
            remaining = normalized_text[:idx] + normalized_text[idx + len(normalized_pattern):]
            return True, remaining.strip()
        return False, normalized_text
    
    def score_artist(self, artists: str, video_title: str, channel: str, 
                     working_title: str, breakdown: ScoreBreakdown) -> str:
        """
        Score artist matches and return updated working title.
        """
        artist_list = [a.strip() for a in artists.split(',')]
        
        for artist in artist_list:
            normalized_artist = self.normalize_text(artist)
            normalized_channel = self.strip_official_suffixes(channel)
            
            found_in_title, new_working = self.find_and_remove(working_title, artist)
            found_in_channel = normalized_artist in normalized_channel
            
            # Check for exact channel match (official artist channel)
            if normalized_artist == normalized_channel:
                breakdown.add_detail(
                    f"artist.channel-exact:{artist}",
                    self.config.ARTIST_CHANNEL_EXACT_MATCH_BONUS,
                    "artist",
                    "Channel is official artist channel"
                )
                if found_in_title:
                    working_title = new_working
            elif found_in_title or found_in_channel:
                breakdown.add_detail(
                    f"artist.match:{artist}",
                    self.config.ARTIST_BONUS_PER_MATCH,
                    "artist",
                    f"Found in {'title' if found_in_title else 'channel'}"
                )
                if found_in_title:
                    working_title = new_working
            else:
                # Try fuzzy match as fallback (e.g., "ø" vs "o")
                fuzzy_artist = self.normalize_for_fuzzy_match(artist)
                fuzzy_found_in_title, fuzzy_new_working = self.find_and_remove(
                    working_title, fuzzy_artist
                )
                fuzzy_channel = self.normalize_for_fuzzy_match(channel)
                fuzzy_found_in_channel = fuzzy_artist in self.normalize_for_fuzzy_match(
                    self.strip_official_suffixes(channel)
                )
                
                if fuzzy_found_in_title or fuzzy_found_in_channel:
                    breakdown.add_detail(
                        f"artist.fuzzy-match:{artist}",
                        self.config.ARTIST_BONUS_PER_FUZZY_MATCH,
                        "artist",
                        f"Fuzzy match in {'title' if fuzzy_found_in_title else 'channel'} (e.g., ø vs o)"
                    )
                    if fuzzy_found_in_title:
                        working_title = fuzzy_new_working
                else:
                    breakdown.add_detail(
                        f"artist.miss:{artist}",
                        self.config.ARTIST_PENALTY_PER_MISS,
                        "artist"
                    )
        
        return working_title
    
    def score_title(self, title: str, working_title: str, 
                    breakdown: ScoreBreakdown) -> Tuple[str, Set[str]]:
        """
        Score title matches and return updated working title and matched tokens.
        """
        normalized_title = self.normalize_text(title)
        matched_tokens = set()
        
        exact_match, new_working = self.find_and_remove(working_title, title)
        
        if exact_match:
            breakdown.add_detail(
                "title.exact",
                self.config.TITLE_EXACT_MATCH_BONUS,
                "title",
                "Exact title match"
            )
            title_tokens = self.tokenize(normalized_title)
            matched_tokens.update(title_tokens)
            return new_working, matched_tokens
        
        title_tokens = self.tokenize(normalized_title)
        working_tokens = self.tokenize(working_title)
        
        for token in title_tokens:
            if token in working_tokens:
                breakdown.add_detail(
                    f"title.token:{token}",
                    self.config.TITLE_TOKEN_BONUS_PER_MATCH,
                    "title"
                )
                working_tokens.remove(token)
                matched_tokens.add(token)
            else:
                breakdown.add_detail(
                    f"title.miss:{token}",
                    self.config.TITLE_TOKEN_PENALTY_PER_MISS,
                    "title"
                )
        
        remaining_working = ' '.join(working_tokens)
        return remaining_working, matched_tokens
    
    def detect_extended_keywords(self, text: str) -> List[str]:
        """Detect extended/club/original mix keywords in text."""
        normalized = self.normalize_text(text)
        found = []
        
        for keyword in self.config.EXTENDED_KEYWORDS:
            if keyword in normalized:
                found.append(keyword)
        
        return found
    
    def score_extended(self, working_title: str, artist_score: float, 
                       title_score: float, remaining_penalty: float,
                       breakdown: ScoreBreakdown, candidate_duration: int = None, 
                       query_duration: int = None) -> Set[str]:
        """
        Score extended version bonus if conditions are met.
        Returns set of extended keyword tokens to exclude from remaining penalty.
        """
        extended_keywords = self.detect_extended_keywords(working_title)
        extended_tokens = set()
        
        if not extended_keywords:
            return extended_tokens
        
        for keyword in extended_keywords:
            tokens = self.tokenize(keyword)
            extended_tokens.update(tokens)
        
        conditions_met = (
            abs(remaining_penalty) <= self.config.EXTENDED_MAX_REMAINING_PENALTY_ALLOWED and
            artist_score >= self.config.EXTENDED_MIN_ARTIST_SCORE and
            title_score >= self.config.EXTENDED_MIN_TITLE_SCORE
        )
        
        if conditions_met:
            breakdown.add_detail(
                f"extended.detected:{', '.join(extended_keywords)}",
                self.config.EXTENDED_LARGE_BONUS,
                "extended",
                "Extended version detected with sufficient match quality"
            )
            
            # Additional bonus if the extended version is appropriately longer
            if candidate_duration and query_duration and candidate_duration > query_duration * 1.3:
                breakdown.add_detail(
                    "extended.duration-bonus",
                    self.config.EXTENDED_DURATION_BONUS,
                    "extended",
                    f"Extended version with appropriate long duration"
                )
        else:
            breakdown.add_detail(
                f"extended.rejected:{', '.join(extended_keywords)}",
                0,
                "extended",
                f"Conditions not met (artist:{artist_score:.0f}, title:{title_score:.0f}, remaining:{remaining_penalty:.0f})"
            )
        
        return extended_tokens
    
    def score_remaining_tokens(self, working_title: str, extended_tokens: Set[str],
                               breakdown: ScoreBreakdown) -> float:
        """
        Score penalty for remaining tokens in working title.
        Excludes extended keyword tokens.
        """
        remaining_tokens = self.tokenize(working_title)
        penalty = 0.0
        
        for token in remaining_tokens:
            if token not in extended_tokens:
                token_penalty = self.config.TITLE_REMAINING_TOKEN_PENALTY
                penalty += token_penalty
                breakdown.add_detail(
                    f"title.remaining-token:{token}",
                    token_penalty,
                    "title"
                )
        
        if penalty < self.config.TITLE_REMAINING_TOKEN_PENALTY_MAX:
            capped_amount = penalty - self.config.TITLE_REMAINING_TOKEN_PENALTY_MAX
            breakdown.add_detail(
                "title.remaining-capped",
                capped_amount,
                "title",
                f"Penalty capped at {self.config.TITLE_REMAINING_TOKEN_PENALTY_MAX}"
            )
            penalty = self.config.TITLE_REMAINING_TOKEN_PENALTY_MAX
        
        return penalty
    
    def score_duration(self, query_duration: int, candidate_duration: int,
                       breakdown: ScoreBreakdown):
        """Score based on duration comparison."""
        if candidate_duration < query_duration:
            breakdown.add_detail(
                "duration.too-short",
                self.config.DURATION_PENALTY_TOO_SHORT,
                "duration",
                f"Candidate shorter than query ({candidate_duration}s < {query_duration}s)"
            )
        elif candidate_duration == query_duration:
            breakdown.add_detail(
                "duration.exact",
                0,
                "duration",
                "Exact duration match"
            )
        else:
            delta = candidate_duration - query_duration
            max_delta = int(query_duration * (self.config.DURATION_MAX_RATIO - 1))
            
            if delta <= max_delta:
                bonus_config = self.config.DURATION_BONUS_RANGE
                # Progressive bonus that increases with duration delta
                # This favors longer versions (likely extended) even without the keyword
                bonus = min(
                    bonus_config["max_bonus"],
                    bonus_config["min_bonus"] + delta * bonus_config["bonus_per_second"]
                )
                breakdown.add_detail(
                    f"duration.bonus:+{delta}s",
                    bonus,
                    "duration",
                    f"Longer but within acceptable range (likely extended version)"
                )
            else:
                # Even beyond max ratio, give a small bonus if it's not excessively long
                # This helps when extended versions are significantly longer
                ratio = candidate_duration / query_duration if query_duration > 0 else 0
                if ratio <= self.config.DURATION_MAX_RATIO * 1.2:  # Up to 2.4x for 2.0 max ratio
                    # Small consolation bonus for moderately over-long versions
                    bonus = 5
                    breakdown.add_detail(
                        f"duration.slightly-too-long:+{delta}s",
                        bonus,
                        "duration",
                        f"Exceeds max ratio but not excessively (ratio: {ratio:.1f}x)"
                    )
                else:
                    breakdown.add_detail(
                        f"duration.too-long:+{delta}s",
                        0,
                        "duration",
                        f"Exceeds max ratio ({self.config.DURATION_MAX_RATIO}x)"
                    )
    
    def score_candidate(self, query: Dict[str, str], candidate: Dict[str, str]) -> ScoreBreakdown:
        """
        Score a single candidate against the query.
        Returns detailed score breakdown.
        """
        breakdown = ScoreBreakdown()
        
        working_title = self.normalize_text(candidate['title'])
        
        # 1. Score artists
        working_title = self.score_artist(
            query['artists'],
            candidate['title'],
            candidate['channel'],
            working_title,
            breakdown
        )
        
        artist_score = breakdown.components['artist']
        
        # 2. Score title
        working_title, matched_tokens = self.score_title(
            query['title'],
            working_title,
            breakdown
        )
        
        title_score = breakdown.components['title']
        
        # 3. Score extended (needs to be before remaining tokens to identify extended keywords)
        remaining_penalty = 0.0
        query_duration = self.parse_duration(query['length'])
        candidate_duration = self.parse_duration(candidate['length'])
        
        extended_tokens = self.score_extended(
            working_title,
            artist_score,
            title_score,
            remaining_penalty,
            breakdown,
            candidate_duration,
            query_duration
        )
        
        # 4. Score remaining tokens
        remaining_penalty = self.score_remaining_tokens(
            working_title,
            extended_tokens,
            breakdown
        )
        
        # 5. Score duration
        self.score_duration(query_duration, candidate_duration, breakdown)
        
        return breakdown
    
    def rank_candidates(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rank all candidates for a query.
        Returns the input data with scores added and candidates sorted by score (descending).
        Tie-breaking: preserve original order from search results.
        """
        query = data['query']
        candidates = data['candidates']
        
        # First pass: score all candidates
        scored_candidates = []
        for idx, candidate in enumerate(candidates):
            breakdown = self.score_candidate(query, candidate)
            scored_candidate = {
                **candidate,
                'score': breakdown.to_dict(),
                '_original_index': idx,  # For tie-breaking
                '_breakdown_obj': breakdown  # Keep for second pass
            }
            scored_candidates.append(scored_candidate)
        
        # Second pass: detect implicit extended versions
        # Find candidates with explicit extended keywords
        query_duration = self.parse_duration(query['length'])
        explicit_extended_durations = []
        
        for candidate in scored_candidates:
            title_lower = self.normalize_text(candidate['title'])
            has_extended_keyword = any(
                keyword in title_lower 
                for keyword in self.config.EXTENDED_KEYWORDS
            )
            if has_extended_keyword:
                duration = self.parse_duration(candidate['length'])
                explicit_extended_durations.append(duration)
        
        # For each candidate without explicit extended keyword
        for candidate in scored_candidates:
            title_lower = self.normalize_text(candidate['title'])
            has_extended_keyword = any(
                keyword in title_lower 
                for keyword in self.config.EXTENDED_KEYWORDS
            )
            
            if not has_extended_keyword and explicit_extended_durations:
                breakdown = candidate['_breakdown_obj']
                candidate_duration = self.parse_duration(candidate['length'])
                
                # Check if this candidate has similar duration to explicit extended versions
                # and has good artist/title scores
                artist_score = breakdown.components['artist']
                title_score = breakdown.components['title']
                
                # Must have minimum quality scores
                if (artist_score >= self.config.EXTENDED_MIN_ARTIST_SCORE and 
                    title_score >= self.config.EXTENDED_MIN_TITLE_SCORE):
                    
                    # Check if duration is similar to explicit extended versions
                    for ext_duration in explicit_extended_durations:
                        duration_diff = abs(candidate_duration - ext_duration)
                        # If within 20 seconds of an explicit extended version
                        if duration_diff <= 20:
                            # And significantly longer than query
                            if candidate_duration > query_duration * 1.3:
                                # Award implicit extended bonus (smaller than explicit)
                                # This helps identify unlabeled extended versions but doesn't make them win over labeled ones
                                implicit_bonus = self.config.EXTENDED_LARGE_BONUS * 0.5  # 50% of explicit bonus
                                breakdown.add_detail(
                                    "extended.implicit",
                                    implicit_bonus,
                                    "extended",
                                    f"Implicit extended version (similar duration to explicit extended: {ext_duration}s)"
                                )
                                # Update the score dict
                                candidate['score'] = breakdown.to_dict()
                                break
        
        # Sort by score descending, then by original index for tie-breaking
        scored_candidates.sort(key=lambda c: (-c['score']['total'], c['_original_index']))
        
        # Remove temporary fields
        for candidate in scored_candidates:
            candidate.pop('_original_index', None)
            candidate.pop('_breakdown_obj', None)
        
        return {
            'query': query,
            'candidates': scored_candidates
        }
