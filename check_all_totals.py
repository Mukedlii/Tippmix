#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers.theoddsapi import fetch_odds_for_sport_key

events = fetch_odds_for_sport_key("soccer_germany_bundesliga")

if events:
    ev = events[0]
    print(f"Event: {ev.get('home_team')} vs {ev.get('away_team')}\n")
    
    print("Checking ALL bookmakers for totals markets:\n")
    
    for bm in ev.get('bookmakers', []):
        for mkt in bm.get('markets', []):
            if mkt.get('key') == 'totals':
                outcomes = mkt.get('outcomes', [])
                if outcomes:
                    points = [out.get('point') for out in outcomes]
                    print(f"  {bm.get('key'):20s} - points: {set(points)}")
                    
                    # Show first outcome detail
                    first = outcomes[0]
                    print(f"    Example: {first.get('name')} @ point {first.get('point')} = {first.get('price')}")
