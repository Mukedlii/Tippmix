#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "acf78bce7a7976c2bc4d028528d4cb2f"

from bot.providers.theoddsapi import fetch_odds_for_sport_key, match_event_to_fixture, get_over_under_for_match

events = fetch_odds_for_sport_key('soccer_germany_bundesliga')
ev = events[0]

print(f"API: '{ev.get('home_team')}' vs '{ev.get('away_team')}'")
print(f"\nMatch tests:")
print(f"  'RB Leipzig' vs 'Hoffenheim': {match_event_to_fixture(ev, 'RB Leipzig', 'Hoffenheim')}")
print(f"  'RB Leipzig' vs 'TSG Hoffenheim': {match_event_to_fixture(ev, 'RB Leipzig', 'TSG Hoffenheim')}")
print(f"  'Leipzig' vs 'Hoffenheim': {match_event_to_fixture(ev, 'Leipzig', 'Hoffenheim')}")

print(f"\nOver/Under test:")
over, under = get_over_under_for_match("RB Leipzig", "TSG Hoffenheim", ['soccer_germany_bundesliga'], line=2.5)
print(f"  Over 2.5: {over}")
print(f"  Under 2.5: {under}")
