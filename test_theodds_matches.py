#!/usr/bin/env python3
"""Test TheOddsAPI for fetching today's matches"""
import os
import datetime
from bot.providers.theoddsapi import fetch_theodds_fixtures

# Set API key
os.environ["ODDS_API_KEY"] = "acf78bce7a7976c2bc4d028528d4cb2f"

today = datetime.date.today().isoformat()
print(f"\n=== Fetching matches via TheOddsAPI for {today} ===\n")

matches = fetch_theodds_fixtures(today)
print(f"\nTotal matches found: {len(matches)}\n")

if matches:
    print("First 10 matches:")
    for i, m in enumerate(matches[:10], 1):
        print(f"{i}. {m['home_team']} vs {m['away_team']}")
        print(f"   League: {m.get('league_name', 'N/A')}")
        print(f"   Kickoff: {m['kickoff_local']}")
        odds = m.get('odds', {})
        if odds:
            print(f"   Odds: 1={odds.get('1', 'N/A')} X={odds.get('X', 'N/A')} 2={odds.get('2', 'N/A')}")
        print()
else:
    print("No matches found!")
