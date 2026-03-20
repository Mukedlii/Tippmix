#!/usr/bin/env python3
"""
Debug Poisson engine with detailed output
"""

import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.storage.poisson_stats import team_goal_rates, league_goal_baseline

def test_data_retrieval():
    """Test that historical data is retrieved correctly"""
    
    print("\n" + "="*60)
    print("DATA RETRIEVAL TEST")
    print("="*60)
    
    # Test team data with both methods
    print("\n1. Arsenal (team_id=42, SofaScore):")
    data1 = team_goal_rates(team_id=42, team_name="Arsenal")
    print(f"   Result: {data1}")
    
    print("\n2. Arsenal (team_id=57, football-data.org):")
    data2 = team_goal_rates(team_id=57)
    print(f"   Result: {data2}")
    
    print("\n3. Arsenal (name only):")
    data3 = team_goal_rates(team_name="Arsenal")
    print(f"   Result: {data3}")
    
    print("\n4. Liverpool (team_id=43, SofaScore):")
    data4 = team_goal_rates(team_id=43, team_name="Liverpool")
    print(f"   Result: {data4}")
    
    print("\n5. Liverpool (team_id=64, football-data.org):")
    data5 = team_goal_rates(team_id=64)
    print(f"   Result: {data5}")
    
    print("\n6. Premier League (league_id=2021):")
    league_data = league_goal_baseline(league_id=2021)
    print(f"   Result: {league_data}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    test_data_retrieval()
