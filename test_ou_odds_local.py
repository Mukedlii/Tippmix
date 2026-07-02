#!/usr/bin/env python3
"""Test Over/Under odds locally."""
import os
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers.theoddsapi import get_over_under_for_match

sport_keys = ["soccer_germany_bundesliga"]

print("Testing Over/Under odds for RB Leipzig vs Hoffenheim...")
over, under = get_over_under_for_match("RB Leipzig", "Hoffenheim", sport_keys, line=2.5)

print(f"\nResults:")
print(f"  Over 2.5: {over}")
print(f"  Under 2.5: {under}")

if over:
    print("\n[OK] SUCCESS! Over/Under odds found!")
else:
    print("\n[FAIL] No Over/Under odds found!")
    
    # Debug: show what we got from API
    from bot.providers.theoddsapi import fetch_odds_for_sport_key
    events = fetch_odds_for_sport_key("soccer_germany_bundesliga")
    
    if events:
        ev = events[0]
        print(f"\nFirst event: {ev.get('home_team')} vs {ev.get('away_team')}")
        print(f"Bookmakers: {len(ev.get('bookmakers', []))}")
        
        for bm in ev.get('bookmakers', [])[:2]:
            print(f"\n  Bookmaker: {bm.get('key')}")
            print(f"  Markets:")
            for mkt in bm.get('markets', []):
                print(f"    - {mkt.get('key')} (line: {mkt.get('line', 'N/A')})")
