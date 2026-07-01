#!/usr/bin/env python3
import os
import json
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers.theoddsapi import fetch_odds_for_sport_key

events = fetch_odds_for_sport_key("soccer_germany_bundesliga")

if events:
    ev = events[0]
    print(f"Event: {ev.get('home_team')} vs {ev.get('away_team')}\n")
    
    for bm in ev.get('bookmakers', [])[:3]:
        print(f"Bookmaker: {bm.get('key')}")
        
        for mkt in bm.get('markets', []):
            if mkt.get('key') == 'totals':
                print(f"\n  TOTALS MARKET FOUND!")
                print(f"  Full structure:")
                print(json.dumps(mkt, indent=4))
                break
        
        print()
