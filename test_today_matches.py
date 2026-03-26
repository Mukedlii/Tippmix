#!/usr/bin/env python3
"""Test today's matches from SofaScore"""
import datetime
from bot.providers.free_fixtures import fetch_sofascore_day

today = datetime.date.today().isoformat()
print(f"\n=== Fetching matches for {today} ===\n")

matches = fetch_sofascore_day(today)
print(f"\nTotal matches found: {len(matches)}\n")

if matches:
    print("First 10 matches:")
    for i, m in enumerate(matches[:10], 1):
        print(f"{i}. {m['home_team']} vs {m['away_team']}")
        print(f"   League: {m['league_name']}")
        print(f"   Kickoff: {m['kickoff_local']}")
        print()
else:
    print("No matches found!")
