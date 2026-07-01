#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers import theoddsapi

# Clear cache
theoddsapi._CACHE.clear()

# Fetch fresh
events = theoddsapi.fetch_odds_for_sport_key('soccer_germany_bundesliga')

print(f'Events: {len(events)}')

if events:
    ev = events[0]
    print(f'\nFirst event: {ev.get("home_team")} vs {ev.get("away_team")}')
    print(f'Bookmakers: {len(ev.get("bookmakers", []))}')
    
    if ev.get('bookmakers'):
        bm = ev['bookmakers'][0]
        markets = [m.get("key") for m in bm.get("markets", [])]
        print(f'First BM ({bm.get("key")}) markets: {markets}')
        
        # Count totals markets across all bookmakers
        totals_count = sum(1 for bm in ev['bookmakers'] for m in bm.get('markets', []) if m.get('key') == 'totals')
        print(f'\nTotal "totals" markets across all BMs: {totals_count}')
