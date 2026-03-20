#!/usr/bin/env python3
"""
Test Poisson engine return structure
"""

import os
import sys
import json

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.poisson_engine import generate_poisson_tips

def test_structure():
    """Test what generate_poisson_tips actually returns"""
    
    test_match = {
        "fixture_id": 999999,
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "home_team_id": 42,
        "away_team_id": 43,
        "league_id": 2021,
        "league_name": "Premier League",
        "country_name": "England",
        "kickoff_local": "2026-03-20T20:00:00",
    }
    
    print("\n" + "="*60)
    print("TESTING generate_poisson_tips RETURN STRUCTURE")
    print("="*60)
    
    result = generate_poisson_tips([test_match])
    
    print("\nReturn value type:", type(result))
    print("\nReturn value keys:", result.keys() if isinstance(result, dict) else "N/A")
    
    print("\nFull result (JSON):")
    print(json.dumps(result, indent=2, default=str))
    
    print("\n" + "="*60)

if __name__ == "__main__":
    test_structure()
