#!/usr/bin/env python3
"""
Test TheOddsAPI team matching
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.providers import theoddsapi

# Set API key
os.environ['ODDS_API_KEY'] = 'acf78bce7a7976c2bc4d028528d4cb2f'

# Fetch events
print("\nFetching soccer_epl events...")
events = theoddsapi.fetch_odds_for_sport_key('soccer_epl')
print(f"Events found: {len(events)}")

# Test matching with LiveScore team names
test_cases = [
    ("AFC Bournemouth", "Manchester United"),
    ("Bournemouth", "Manchester United"),
    ("RB Leipzig", "Hoffenheim"),
]

print("\nTesting team name matching:")
print("="*60)

for home, away in test_cases:
    print(f"\nTest: {home} vs {away}")
    
    # Try to find match
    found = False
    for event in events:
        if theoddsapi.match_event_to_fixture(event, home, away):
            print(f"  MATCH FOUND!")
            print(f"  TheOddsAPI: {event['home_team']} vs {event['away_team']}")
            
            # Get odds
            o1, ox, o2 = theoddsapi._extract_best_h2h(event)
            print(f"  Odds: {o1} / {ox} / {o2}")
            found = True
            break
    
    if not found:
        print(f"  NO MATCH")
        print(f"  Available teams in events:")
        for e in events[:5]:
            print(f"    - {e['home_team']} vs {e['away_team']}")
