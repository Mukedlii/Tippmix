#!/usr/bin/env python3
"""
Team Name Matching Utility

Matches team names from different providers (SofaScore, football-data.org, etc.)
to enable historical data lookup even when team IDs don't match.

Strategy:
1. Normalize team names (lowercase, remove FC/AFC/etc.)
2. Fuzzy match using Levenshtein distance
3. Cache mappings for performance
"""

import os
import sqlite3
from typing import Optional, Dict, Tuple
from difflib import SequenceMatcher

from bot.storage.sqlite_store import _db_path


# Team name normalization patterns
TEAM_PREFIXES = ["fc", "afc", "sfc", "bfc", "rfc", "asc", "sc", "us", "ac", "ss", "tsg"]
TEAM_SUFFIXES = ["fc", "city", "town", "athletic", "wanderers"]  # Removed "united" - it's often part of the core name


def normalize_team_name(name: str) -> str:
    """Normalize team name for matching"""
    if not name:
        return ""
    
    # Lowercase
    name = name.lower().strip()
    
    # Remove common prefixes/suffixes
    words = name.split()
    if len(words) > 1:
        # Remove prefix (but only if we still have 1+ words left)
        if words[0] in TEAM_PREFIXES and len(words) > 1:
            words = words[1:]
        # Remove suffix (but only if we still have 1+ words left)
        if len(words) > 1 and words[-1] in TEAM_SUFFIXES:
            words = words[:-1]
    
    # Remove special chars and numbers (TSG 1899 Hoffenheim → TSG Hoffenheim)
    name = " ".join(words)
    name = name.replace("'", "").replace("-", " ")
    # Remove standalone numbers
    words = [w for w in name.split() if not w.isdigit()]
    name = " ".join(words)
    
    return name.strip()


def similarity_score(s1: str, s2: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0)"""
    return SequenceMatcher(None, s1, s2).ratio()


class TeamMatcher:
    """
    Maps team names from different providers to a unified team identifier.
    
    Uses both exact name matching and fuzzy matching to find historical data
    even when provider team IDs differ.
    """
    
    def __init__(self):
        self._cache: Dict[str, Optional[int]] = {}
        self._team_names_by_id: Dict[int, str] = {}
        self._load_historical_teams()
    
    def _load_historical_teams(self):
        """Load team names and IDs from historical results"""
        if not os.path.exists(_db_path()):
            return
        
        con = sqlite3.connect(_db_path())
        con.row_factory = sqlite3.Row
        
        try:
            # Extract team names from raw_json in results table
            rows = con.execute("""
                SELECT DISTINCT home_team_id, raw_json
                FROM results
                WHERE home_team_id IS NOT NULL
                  AND raw_json IS NOT NULL
            """).fetchall()
            
            import json
            for row in rows:
                try:
                    data = json.loads(row["raw_json"])
                    home_team = data.get("teams", {}).get("home", {})
                    team_id = home_team.get("id")
                    team_name = home_team.get("name")
                    
                    if team_id and team_name:
                        self._team_names_by_id[team_id] = team_name
                except Exception:
                    pass
            
            # Also check away teams
            rows = con.execute("""
                SELECT DISTINCT away_team_id, raw_json
                FROM results
                WHERE away_team_id IS NOT NULL
                  AND raw_json IS NOT NULL
            """).fetchall()
            
            for row in rows:
                try:
                    data = json.loads(row["raw_json"])
                    away_team = data.get("teams", {}).get("away", {})
                    team_id = away_team.get("id")
                    team_name = away_team.get("name")
                    
                    if team_id and team_name:
                        self._team_names_by_id[team_id] = team_name
                except Exception:
                    pass
            
        finally:
            con.close()
    
    def find_team_id(self, team_name: str, min_similarity: float = 0.85) -> Optional[int]:
        """
        Find team ID from historical data by matching team name.
        
        Args:
            team_name: Team name from current match (e.g., from SofaScore)
            min_similarity: Minimum similarity score for fuzzy match (0.0-1.0)
        
        Returns:
            team_id from historical data (football-data.org ID) or None
        """
        if not team_name:
            return None
        
        # Check cache first
        cache_key = team_name.lower()
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Normalize input
        normalized_input = normalize_team_name(team_name)
        
        # Try exact match first
        for team_id, historical_name in self._team_names_by_id.items():
            normalized_historical = normalize_team_name(historical_name)
            if normalized_input == normalized_historical:
                self._cache[cache_key] = team_id
                return team_id
        
        # Fuzzy match
        best_match: Optional[Tuple[int, float]] = None
        for team_id, historical_name in self._team_names_by_id.items():
            normalized_historical = normalize_team_name(historical_name)
            score = similarity_score(normalized_input, normalized_historical)
            
            if score >= min_similarity:
                if best_match is None or score > best_match[1]:
                    best_match = (team_id, score)
        
        if best_match:
            team_id, score = best_match
            self._cache[cache_key] = team_id
            return team_id
        
        # No match found
        self._cache[cache_key] = None
        return None
    
    def get_team_name(self, team_id: int) -> Optional[str]:
        """Get team name for a historical team ID"""
        return self._team_names_by_id.get(team_id)


# Global instance
_matcher: Optional[TeamMatcher] = None


def get_matcher() -> TeamMatcher:
    """Get or create global TeamMatcher instance"""
    global _matcher
    if _matcher is None:
        _matcher = TeamMatcher()
    return _matcher


def find_historical_team_id(team_name: str) -> Optional[int]:
    """
    Find historical team ID by name (convenience function).
    
    Args:
        team_name: Team name from current match provider
    
    Returns:
        Historical team ID (football-data.org) or None
    """
    return get_matcher().find_team_id(team_name)
