#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers.theoddsapi import fetch_odds_for_sport_key

events = fetch_odds_for_sport_key('soccer_germany_bundesliga')

print(f"Total Bundesliga events: {len(events)}\n")

for i, ev in enumerate(events, 1):
    home = ev.get('home_team', '')
    away = ev.get('away_team', '')
    time = ev.get('commence_time', '')[:16]
    
    print(f"{i:2d}. {home:25s} vs {away:25s} @ {time}")
