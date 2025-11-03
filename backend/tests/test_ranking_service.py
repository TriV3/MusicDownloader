"""
Tests for the ranking service using the test cases from docs/search_ranking_cases.json
"""

import json
import unittest
from pathlib import Path

from backend.app.utils.ranking_service import RankingService
from backend.app.utils.ranking_config import RankingConfig


class TestRankingService(unittest.TestCase):
    """Test the ranking service against known test cases."""
    
    @classmethod
    def setUpClass(cls):
        """Load test cases from JSON file."""
        test_cases_path = Path(__file__).parent.parent.parent / 'docs' / 'search_ranking_cases.json'
        with open(test_cases_path, 'r', encoding='utf-8') as f:
            cls.test_cases = json.load(f)
        cls.ranking_service = RankingService()
    
    def test_all_cases(self):
        """Test all cases from the JSON file."""
        failed_cases = []
        
        for i, test_case in enumerate(self.test_cases, 1):
            with self.subTest(case=i):
                result = self.ranking_service.rank_candidates(test_case)
                
                winner_id = result['candidates'][0]['id']
                
                # Support both single expected_winner and list of expected_winners
                if 'expected_winners' in test_case:
                    expected_winners = test_case['expected_winners']
                elif 'expected_winner' in test_case:
                    expected_winners = [test_case['expected_winner']]
                else:
                    self.fail(f"Case {i}: No expected_winner or expected_winners specified")
                
                if winner_id not in expected_winners:
                    failed_cases.append({
                        'case_number': i,
                        'query': test_case['query'],
                        'expected': expected_winners,
                        'actual': winner_id,
                        'top_3': [
                            {
                                'id': c['id'],
                                'title': c['title'],
                                'score': c['score']['total']
                            }
                            for c in result['candidates'][:3]
                        ]
                    })
        
        if failed_cases:
            error_msg = "\n\nFailed test cases:\n"
            for failure in failed_cases:
                error_msg += f"\nCase {failure['case_number']}:\n"
                error_msg += f"  Query: {failure['query']['artists']} - {failure['query']['title']}\n"
                expected_str = ', '.join(failure['expected']) if isinstance(failure['expected'], list) else failure['expected']
                error_msg += f"  Expected (any of): {expected_str}\n"
                error_msg += f"  Actual: {failure['actual']}\n"
                error_msg += f"  Top 3 scores:\n"
                for candidate in failure['top_3']:
                    error_msg += f"    {candidate['id']}: {candidate['score']:.2f} - {candidate['title']}\n"
            
            self.fail(error_msg)
    
    def test_score_breakdown_structure(self):
        """Test that score breakdown has the expected structure."""
        test_case = self.test_cases[0]
        result = self.ranking_service.rank_candidates(test_case)
        
        for candidate in result['candidates']:
            self.assertIn('score', candidate)
            score = candidate['score']
            
            self.assertIn('total', score)
            self.assertIsInstance(score['total'], (int, float))
            
            self.assertIn('components', score)
            components = score['components']
            self.assertIn('artist', components)
            self.assertIn('title', components)
            self.assertIn('extended', components)
            self.assertIn('duration', components)
            
            self.assertIn('details', score)
            self.assertIsInstance(score['details'], list)
            
            for detail in score['details']:
                self.assertIn('key', detail)
                self.assertIn('value', detail)
                self.assertIn('family', detail)
                self.assertIn(detail['family'], ['artist', 'title', 'extended', 'duration'])
    
    def test_normalization(self):
        """Test text normalization."""
        service = self.ranking_service
        
        self.assertEqual(service.normalize_text("Block & Crown"), "block & crown")
        self.assertEqual(service.normalize_text("AUSMAX"), "ausmax")
        self.assertEqual(service.normalize_text("Nessø"), "nessø")
    
    def test_duration_parsing(self):
        """Test duration parsing."""
        service = self.ranking_service
        
        self.assertEqual(service.parse_duration("2:39"), 159)
        self.assertEqual(service.parse_duration("3:07"), 187)
        self.assertEqual(service.parse_duration("1:23:45"), 5025)
        self.assertEqual(service.parse_duration("0:30"), 30)
    
    def test_official_suffix_stripping(self):
        """Test stripping of official channel suffixes."""
        service = self.ranking_service
        
        self.assertEqual(service.strip_official_suffixes("AUSMAX - Topic"), "ausmax")
        self.assertEqual(service.strip_official_suffixes("Block & Crown - Official"), "block & crown")
        self.assertEqual(service.strip_official_suffixes("Artist Official"), "artist")
        self.assertEqual(service.strip_official_suffixes("SomeVEVO"), "some")
    
    def test_tokenization(self):
        """Test tokenization preserves important symbols."""
        service = self.ranking_service
        
        tokens = service.tokenize("Block & Crown - Lonely Heart")
        self.assertIn("block", tokens)
        self.assertIn("&", tokens)
        self.assertIn("crown", tokens)
        self.assertIn("lonely", tokens)
        self.assertIn("heart", tokens)
    
    def test_find_and_remove(self):
        """Test the find and remove functionality."""
        service = self.ranking_service
        
        found, remaining = service.find_and_remove("block & crown - lonely heart", "block & crown")
        self.assertTrue(found)
        self.assertEqual(remaining, "- lonely heart")
        
        found, remaining = service.find_and_remove("lonely heart official video", "lonely heart")
        self.assertTrue(found)
        self.assertIn("official", remaining)
        self.assertIn("video", remaining)
    
    def test_extended_keywords_detection(self):
        """Test detection of extended keywords."""
        service = self.ranking_service
        
        keywords = service.detect_extended_keywords("Block & Crown - Lonely Heart (Extended Mix)")
        self.assertIn("extended", keywords)
        
        keywords = service.detect_extended_keywords("Some Track (Club Mix)")
        self.assertIn("club", keywords)
        
        keywords = service.detect_extended_keywords("Original Mix Version")
        self.assertIn("original mix", keywords)
        
        keywords = service.detect_extended_keywords("Just a regular title")
        self.assertEqual(len(keywords), 0)


if __name__ == '__main__':
    unittest.main()
