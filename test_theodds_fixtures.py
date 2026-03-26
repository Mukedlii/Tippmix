#!/usr/bin/env python3
"""Test TheOddsAPI as primary fixture source"""
import os
import datetime

os.environ["ODDS_API_KEY"] = "acf78bce7a7976c2bc4d028528d4cb2f"
os.environ["ODDS_MAX_SPORT_KEYS"] = "12"  # Use all top leagues

from bot.providers.theodds_fixtures import fetch_theodds_fixtures

today = datetime.date.today().isoformat()
print(f"\n=== TheOddsAPI as Primary Source ===")
print(f"Date: {today}\n")

matches = fetch_theodds_fixtures(today)

print(f"\nTotal matches: {len(matches)}")
print(f"With full odds: {sum(1 for m in matches if m.get('odds', {}).get('1'))}\n")

if matches:
    print("Sample matches:\n")
    for i, m in enumerate(matches[:15], 1):
        odds = m.get('odds', {})
        print(f"{i}. {m['home_team']} vs {m['away_team']}")
        print(f"   League: {m['league_name']}")
        print(f"   Kickoff: {m['kickoff_local']}")
        if odds.get('1'):
            print(f"   Odds: 1={odds['1']} X={odds['X']} 2={odds['2']}")
        else:
            print(f"   Odds: N/A")
        print()
