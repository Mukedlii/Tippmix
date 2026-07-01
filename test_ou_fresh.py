#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers import theoddsapi

# Clear cache
theoddsapi._CACHE.clear()

# Test Over/Under
over, under = theoddsapi.get_over_under_for_match(
    "RB Leipzig",
    "TSG Hoffenheim",
    ["soccer_germany_bundesliga"],
    line=2.5
)

print(f"Over 2.5: {over}")
print(f"Under 2.5: {under}")

if over:
    print("\n[OK] Success!")
else:
    print("\n[FAIL] Still None - investigating...")
    
    events = theoddsapi.fetch_odds_for_sport_key("soccer_germany_bundesliga")
    for ev in events:
        if theoddsapi.match_event_to_fixture(ev, "RB Leipzig", "TSG Hoffenheim"):
            print(f"  Match found: {ev.get('home_team')} vs {ev.get('away_team')}")
            totals_count = sum(1 for bm in ev.get('bookmakers', []) for m in bm.get('markets', []) if m.get('key') == 'totals')
            print(f"  Totals markets: {totals_count}")
            break
