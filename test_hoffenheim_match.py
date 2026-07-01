#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers.theoddsapi import fetch_odds_for_sport_key, match_event_to_fixture

events = fetch_odds_for_sport_key('soccer_germany_bundesliga')

print(f"Total events: {len(events)}\n")

# Find RB Leipzig
for ev in events:
    home = ev.get('home_team', '')
    away = ev.get('away_team', '')
    
    if 'Leipzig' in home or 'Leipzig' in away:
        print(f"Found: '{home}' vs '{away}'")
        
        # Test matching
        print(f"\nMatching tests:")
        print(f"  'RB Leipzig' vs 'Hoffenheim': {match_event_to_fixture(ev, 'RB Leipzig', 'Hoffenheim')}")
        print(f"  'RB Leipzig' vs 'TSG Hoffenheim': {match_event_to_fixture(ev, 'RB Leipzig', 'TSG Hoffenheim')}")
        print(f"  'Leipzig' vs 'Hoffenheim': {match_event_to_fixture(ev, 'Leipzig', 'Hoffenheim')}")
        break
