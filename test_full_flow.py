#!/usr/bin/env python3
"""Test full flow: fetch matches + enrich odds"""
import os
import datetime

# Set environment
os.environ["SPORTS_DATA_PROVIDER"] = "free_scraper"
os.environ["ODDS_API_KEY"] = "acf78bce7a7976c2bc4d028528d4cb2f"
os.environ["TIPPMIX_SLOT"] = "DAY"
os.environ["ODDS_MAX_REQUESTS_PER_RUN"] = "10"

from bot.matches import fetch_matches_for_today

print("\n=== Full Flow Test ===\n")
print("Provider: free_scraper (LiveScore fallback)")
print("Odds: TheOddsAPI\n")

matches = fetch_matches_for_today()

print(f"\nTotal matches: {len(matches)}")
print(f"With odds: {sum(1 for m in matches if m.get('odds', {}).get('1'))}")

print("\n=== Sample matches with odds ===\n")
with_odds = [m for m in matches if m.get('odds', {}).get('1')]
for i, m in enumerate(with_odds[:10], 1):
    odds = m['odds']
    print(f"{i}. {m['home_team']} vs {m['away_team']}")
    print(f"   League: {m['league_name']}")
    print(f"   Odds: 1={odds.get('1', 'N/A')} X={odds.get('X', 'N/A')} 2={odds.get('2', 'N/A')}")
    print(f"   Source: {m.get('odds_source', 'unknown')}")
    print()
