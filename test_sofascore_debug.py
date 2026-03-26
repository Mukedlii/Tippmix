#!/usr/bin/env python3
"""Debug SofaScore API call"""
import requests
import datetime

date_str = datetime.date.today().isoformat()
url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
}

print(f"\nURL: {url}")
print(f"Headers: {headers}\n")

try:
    r = requests.get(url, headers=headers, timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Headers: {dict(r.headers)}\n")
    
    if r.status_code == 200:
        data = r.json()
        events = data.get("events", [])
        print(f"Events: {len(events)}")
        if events:
            print(f"\nFirst event: {events[0]}")
    else:
        print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
