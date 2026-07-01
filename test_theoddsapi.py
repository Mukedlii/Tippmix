#!/usr/bin/env python3
"""
Test TheOddsAPI connection and quota
"""
import os
import sys
import requests

# Set API key from TOOLS.md
API_KEY = "<your_odds_api_key>"

print("\n" + "="*60)
print("THEODDSAPI TEST")
print("="*60)

# Test Premier League
url = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
params = {
    "apiKey": API_KEY,
    "regions": "eu",
    "markets": "h2h",
    "oddsFormat": "decimal",
}

print(f"\nTesting: {url}")
print(f"Params: {params}")

try:
    r = requests.get(url, params=params, timeout=15)
    
    print(f"\nStatus: {r.status_code}")
    print(f"Remaining requests: {r.headers.get('x-requests-remaining', 'N/A')}")
    print(f"Used requests: {r.headers.get('x-requests-used', 'N/A')}")
    
    if r.status_code == 200:
        data = r.json()
        print(f"Events found: {len(data)}")
        
        if data:
            print("\nSample event:")
            event = data[0]
            print(f"  Home: {event.get('home_team')}")
            print(f"  Away: {event.get('away_team')}")
            print(f"  Commence: {event.get('commence_time')}")
            print(f"  Bookmakers: {len(event.get('bookmakers', []))}")
    else:
        print(f"Error: {r.text[:500]}")
        
except Exception as e:
    print(f"Exception: {e}")

print("\n" + "="*60)
