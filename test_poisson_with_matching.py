#!/usr/bin/env python3
"""
Test Poisson engine with team name matching
"""

import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.poisson_engine import generate_poisson_tips
from bot.storage.team_matcher import get_matcher

def test_poisson():
    """Test Poisson prediction with team name matching"""
    
    # Example match: Arsenal vs Liverpool (both in historical data)
    test_match = {
        "fixture_id": 999999,
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "home_team_id": 42,  # SofaScore ID (different from football-data.org)
        "away_team_id": 43,  # SofaScore ID (different from football-data.org)
        "league_id": 2021,  # Premier League (football-data.org)
        "league_name": "Premier League",
        "country_name": "England",
        "kickoff_local": "2026-03-20T20:00:00",
    }
    
    print("\n" + "="*60)
    print("POISSON ENGINE TEST WITH TEAM NAME MATCHING")
    print("="*60)
    
    # Show team matching
    matcher = get_matcher()
    print(f"\nMatch: {test_match['home_team']} vs {test_match['away_team']}")
    print(f"Provider IDs: {test_match['home_team_id']} vs {test_match['away_team_id']}")
    
    home_hist_id = matcher.find_team_id(test_match['home_team'])
    away_hist_id = matcher.find_team_id(test_match['away_team'])
    
    print(f"\nHistorical IDs found:")
    print(f"  {test_match['home_team']}: {home_hist_id} ({matcher.get_team_name(home_hist_id) if home_hist_id else 'N/A'})")
    print(f"  {test_match['away_team']}: {away_hist_id} ({matcher.get_team_name(away_hist_id) if away_hist_id else 'N/A'})")
    
    # Generate tips
    print("\n" + "="*60)
    print("GENERATING TIPS...")
    print("="*60)
    
    result = generate_poisson_tips([test_match])
    
    if result.get("safe_picks"):
        print("\n[SAFE] SAFE PICKS:")
        for pick in result["safe_picks"]:
            print(f"  {pick['home_team']} vs {pick['away_team']}")
            print(f"    Market: {pick['market']}")
            print(f"    Pick: {pick['pick']}")
            print(f"    Probability: {pick['p']:.1%}")
            print(f"    Data quality: {pick.get('data_quality', 'N/A')}")
            print()
    
    if result.get("risk_picks"):
        print("\n[RISK] RISK PICKS:")
        for pick in result["risk_picks"]:
            print(f"  {pick['home_team']} vs {pick['away_team']}")
            print(f"    Market: {pick['market']}")
            print(f"    Pick: {pick['pick']}")
            print(f"    Probability: {pick['p']:.1%}")
            print()
    
    if not result.get("safe_picks") and not result.get("risk_picks"):
        print("\n[!!] No picks generated (check if historical data exists)")
    
    print("="*60)

if __name__ == "__main__":
    test_poisson()
