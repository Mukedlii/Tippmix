#!/usr/bin/env python3
"""Check what dates have upcoming matches"""
import os
import requests
import datetime
from collections import defaultdict

os.environ["ODDS_API_KEY"] = "acf78bce7a7976c2bc4d028528d4cb2f"

api_key = os.environ["ODDS_API_KEY"]
sport_key = "soccer_epl"  # Premier League

url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
params = {
    "apiKey": api_key,
    "regions": "eu",
    "markets": "h2h",
    "oddsFormat": "decimal",
}

print(f"\n=== Checking upcoming events for {sport_key} ===\n")

r = requests.get(url, params=params, timeout=25)
print(f"Status: {r.status_code}")
print(f"Quota remaining: {r.headers.get('x-requests-remaining', 'N/A')}")

if r.status_code == 200:
    events = r.json()
    print(f"Total events: {len(events)}\n")
    
    # Group by date
    by_date = defaultdict(list)
    for ev in events:
        commence = ev.get("commence_time", "")
        if not commence:
            continue
        try:
            dt = datetime.datetime.fromisoformat(commence.replace("Z", "+00:00"))
            date_str = dt.date().isoformat()
            by_date[date_str].append(f"{ev.get('home_team')} vs {ev.get('away_team')}")
        except:
            continue
    
    print("Events by date:")
    for date in sorted(by_date.keys()):
        print(f"\n{date}: {len(by_date[date])} matches")
        for match in by_date[date][:3]:
            print(f"  - {match}")
else:
    print(f"Error: {r.text[:500]}")
