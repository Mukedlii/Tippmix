#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "acf78bce7a7976c2bc4d028528d4cb2f"

from bot.providers import theoddsapi

# Fetch Bundesliga
events = theoddsapi.fetch_odds_for_sport_key('soccer_germany_bundesliga')
print(f"Total events: {len(events)}\n")

# Show first 3 team names from API
for i, ev in enumerate(events[:3]):
    print(f"{i+1}. {ev.get('home_team')} vs {ev.get('away_team')}")

print("\n=== MATCHING TESTS ===")

# Test different variations
ev = events[0]  # RB Leipzig vs TSG Hoffenheim
print(f"\nAPI teams: '{ev.get('home_team')}' vs '{ev.get('away_team')}'")

test_cases = [
    ("RB Leipzig", "Hoffenheim"),
    ("RB Leipzig", "TSG Hoffenheim"),
    ("Leipzig", "Hoffenheim"),
    ("RB Leipzig", "TSG 1899 Hoffenheim"),
]

for home, away in test_cases:
    result = theoddsapi.match_event_to_fixture(ev, home, away)
    print(f"  '{home}' vs '{away}' => {result}")

# Get actual odds
print("\n=== ODDS EXTRACTION ===")
o1, ox, o2 = theoddsapi.get_1x2_for_match("RB Leipzig", "Hoffenheim", ['soccer_germany_bundesliga'])
print(f"Odds: 1={o1}, X={ox}, 2={o2}")
