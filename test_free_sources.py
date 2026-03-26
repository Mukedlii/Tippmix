#!/usr/bin/env python3
"""Test all free fixture sources"""
import datetime
from bot.providers.free_fixtures import (
    fetch_sofascore_day,
    fetch_livescore_day,
    fetch_flashscore_day,
)

today = datetime.date.today().isoformat()
print(f"\n=== Testing free sources for {today} ===\n")

print("1. SofaScore:")
sofascore = fetch_sofascore_day(today)
print(f"   Found: {len(sofascore)} matches\n")

print("2. LiveScore:")
livescore = fetch_livescore_day(today)
print(f"   Found: {len(livescore)} matches")
if livescore:
    for i, m in enumerate(livescore[:3], 1):
        print(f"   {i}. {m['home_team']} vs {m['away_team']} ({m['league_name']})")
print()

print("3. Flashscore:")
flashscore = fetch_flashscore_day(today)
print(f"   Found: {len(flashscore)} matches")
if flashscore:
    for i, m in enumerate(flashscore[:3], 1):
        print(f"   {i}. {m['home_team']} vs {m['away_team']} ({m['league_name']})")
print()

print(f"\nBest source: ", end="")
if len(sofascore) > 0:
    print(f"SofaScore ({len(sofascore)} matches)")
elif len(livescore) > 0:
    print(f"LiveScore ({len(livescore)} matches)")
elif len(flashscore) > 0:
    print(f"Flashscore ({len(flashscore)} matches)")
else:
    print("None working!")
