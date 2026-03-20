#!/usr/bin/env python3
"""
League Name Matching Utility

Matches league names from different providers to enable historical data lookup.

Strategy:
1. Normalize league names (remove "England", "Germany", etc.)
2. Fuzzy match using SequenceMatcher
3. Cache mappings for performance
"""

import os
import sqlite3
from typing import Optional, Dict, Tuple
from difflib import SequenceMatcher

from bot.storage.sqlite_store import _db_path


# League name normalization patterns
COUNTRY_PREFIXES = [
    "england", "germany", "spain", "italy", "france", "portugal", "netherlands",
    "scotland", "belgium", "austria", "turkey", "russia", "greece", "ukraine",
    "croatia", "serbia", "switzerland", "denmark", "norway", "sweden", "poland",
    "czech", "romania", "hungary", "slovakia", "bulgaria"
]


def normalize_league_name(name: str) -> str:
    """Normalize league name for matching"""
    if not name:
        return ""
    
    # Lowercase
    name = name.lower().strip()
    
    # Remove country prefix
    words = name.split()
    if len(words) > 1 and words[0] in COUNTRY_PREFIXES:
        words = words[1:]
    
    # Common replacements
    name = " ".join(words)
    name = name.replace("1.", "").replace("2.", "")  # Bundesliga 1. → Bundesliga
    name = name.replace("division", "div")
    name = name.replace("championship", "champ")
    
    # Remove special chars
    name = name.replace("'", "").replace("-", " ")
    
    # Trim
    name = " ".join(name.split())
    
    return name.strip()


def similarity_score(s1: str, s2: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0)"""
    return SequenceMatcher(None, s1, s2).ratio()


class LeagueMatcher:
    """
    Maps league names from different providers to a unified league identifier.
    
    Uses both exact name matching and fuzzy matching to find historical data
    even when provider league IDs differ.
    """
    
    def __init__(self):
        self._cache: Dict[str, Optional[int]] = {}
        self._league_names_by_id: Dict[int, str] = {}
        self._load_historical_leagues()
    
    def _load_historical_leagues(self):
        """Load league names and IDs from historical results"""
        if not os.path.exists(_db_path()):
            return
        
        con = sqlite3.connect(_db_path())
        con.row_factory = sqlite3.Row
        
        try:
            # Extract league names from raw_json in results table
            rows = con.execute("""
                SELECT DISTINCT league_id, raw_json
                FROM results
                WHERE league_id IS NOT NULL
                  AND raw_json IS NOT NULL
                LIMIT 1000
            """).fetchall()
            
            import json
            for row in rows:
                try:
                    data = json.loads(row["raw_json"])
                    league = data.get("league", {})
                    league_id = league.get("id")
                    league_name = league.get("name")
                    
                    if league_id and league_name:
                        # Keep the first name we see for each ID
                        if league_id not in self._league_names_by_id:
                            self._league_names_by_id[league_id] = league_name
                except Exception:
                    pass
            
        finally:
            con.close()
    
    def find_league_id(self, league_name: str, min_similarity: float = 0.75) -> Optional[int]:
        """
        Find league ID from historical data by matching league name.
        
        Args:
            league_name: League name from current match (e.g., "England Premier League")
            min_similarity: Minimum similarity score for fuzzy match (0.0-1.0)
        
        Returns:
            league_id from historical data (football-data.org ID) or None
        """
        if not league_name:
            return None
        
        # Check cache first
        cache_key = league_name.lower()
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Normalize input
        normalized_input = normalize_league_name(league_name)
        
        # Try exact match first
        for league_id, historical_name in self._league_names_by_id.items():
            normalized_historical = normalize_league_name(historical_name)
            if normalized_input == normalized_historical:
                self._cache[cache_key] = league_id
                return league_id
        
        # Fuzzy match
        best_match: Optional[Tuple[int, float]] = None
        for league_id, historical_name in self._league_names_by_id.items():
            normalized_historical = normalize_league_name(historical_name)
            score = similarity_score(normalized_input, normalized_historical)
            
            if score >= min_similarity:
                if best_match is None or score > best_match[1]:
                    best_match = (league_id, score)
        
        if best_match:
            league_id, score = best_match
            self._cache[cache_key] = league_id
            return league_id
        
        # No match found
        self._cache[cache_key] = None
        return None
    
    def get_league_name(self, league_id: int) -> Optional[str]:
        """Get league name for a historical league ID"""
        return self._league_names_by_id.get(league_id)


# Global instance
_matcher: Optional[LeagueMatcher] = None


def get_matcher() -> LeagueMatcher:
    """Get or create global LeagueMatcher instance"""
    global _matcher
    if _matcher is None:
        _matcher = LeagueMatcher()
    return _matcher


def find_historical_league_id(league_name: str) -> Optional[int]:
    """
    Find historical league ID by name (convenience function).
    
    Args:
        league_name: League name from current match provider
    
    Returns:
        Historical league ID (football-data.org) or None
    """
    return get_matcher().find_league_id(league_name)
