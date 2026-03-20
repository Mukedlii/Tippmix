#!/usr/bin/env python3
"""
Test league name matching
"""

import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.storage.league_matcher import get_matcher, normalize_league_name

def test_matcher():
    """Test the league matcher with common league names"""
    matcher = get_matcher()
    
    print("\n" + "="*60)
    print("LEAGUE MATCHER TEST")
    print("="*60)
    
    # Show how many historical leagues loaded
    print(f"\nHistorical leagues loaded: {len(matcher._league_names_by_id)}")
    
    # Show sample historical leagues
    print("\nSample historical leagues:")
    for i, (league_id, league_name) in enumerate(list(matcher._league_names_by_id.items())[:10]):
        print(f"  {league_id}: {league_name}")
    
    # Test matching common variations
    test_cases = [
        "England Premier League",
        "Premier League",
        "Germany Bundesliga",
        "Bundesliga",
        "Spain La Liga",
        "La Liga",
        "Italy Serie A",
        "Serie A",
        "France Ligue 1",
        "Ligue 1",
    ]
    
    print("\n" + "="*60)
    print("MATCHING TESTS")
    print("="*60)
    
    for test_name in test_cases:
        matched_id = matcher.find_league_id(test_name)
        normalized = normalize_league_name(test_name)
        
        if matched_id:
            historical_name = matcher.get_league_name(matched_id)
            print(f"\n[OK] MATCH: '{test_name}'")
            print(f"   Normalized: '{normalized}'")
            print(f"   -> ID {matched_id}: {historical_name}")
        else:
            print(f"\n[!!] NO MATCH: '{test_name}'")
            print(f"   Normalized: '{normalized}'")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    test_matcher()
