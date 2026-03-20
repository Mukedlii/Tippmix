#!/usr/bin/env python3
"""
Test team name matching
"""

import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.storage.team_matcher import get_matcher, normalize_team_name

def test_matcher():
    """Test the team matcher with common team names"""
    matcher = get_matcher()
    
    print("\n" + "="*60)
    print("TEAM MATCHER TEST")
    print("="*60)
    
    # Show how many historical teams loaded
    print(f"\nHistorical teams loaded: {len(matcher._team_names_by_id)}")
    
    # Show sample historical teams
    print("\nSample historical teams (first 10):")
    for i, (team_id, team_name) in enumerate(list(matcher._team_names_by_id.items())[:10]):
        print(f"  {team_id}: {team_name}")
    
    # Test matching common variations
    test_cases = [
        "Arsenal",
        "Arsenal FC",
        "FC Arsenal",
        "Manchester United",
        "Manchester Utd",
        "Man United",
        "Bayern Munich",
        "FC Bayern München",
        "Liverpool",
        "Liverpool FC",
        "Real Madrid",
        "Paris Saint-Germain",
        "PSG",
    ]
    
    print("\n" + "="*60)
    print("MATCHING TESTS")
    print("="*60)
    
    for test_name in test_cases:
        matched_id = matcher.find_team_id(test_name)
        normalized = normalize_team_name(test_name)
        
        if matched_id:
            historical_name = matcher.get_team_name(matched_id)
            print(f"\n[OK] MATCH: '{test_name}'")
            print(f"   Normalized: '{normalized}'")
            print(f"   -> ID {matched_id}: {historical_name}")
        else:
            print(f"\n[!!] NO MATCH: '{test_name}'")
            print(f"   Normalized: '{normalized}'")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    test_matcher()
