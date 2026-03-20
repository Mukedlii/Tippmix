#!/usr/bin/env python3
import json
import os

# Check VIP bets
if os.path.exists('vip_bets_day.json'):
    with open('vip_bets_day.json', 'r', encoding='utf-8') as f:
        vip_bets = json.load(f)
    
    print(f"\nVIP Bets: {len(vip_bets)}")
    print("="*60)
    
    for i, bet in enumerate(vip_bets[:3], 1):
        print(f"\n#{i}: {bet.get('home_team')} vs {bet.get('away_team')}")
        print(f"  odds_estimate: {bet.get('odds_estimate')}")
        print(f"  odds_source: {bet.get('odds_source')}")
        print(f"  odds (raw): {bet.get('odds')}")
        
        # Check raw_json
        raw = bet.get('raw_json')
        if raw:
            if isinstance(raw, str):
                raw = json.loads(raw)
            print(f"  raw odds: {raw.get('odds')}")
else:
    print("vip_bets_day.json not found")

# Check meta
if os.path.exists('vip_bets_day_meta.json'):
    with open('vip_bets_day_meta.json', 'r', encoding='utf-8') as f:
        meta = json.load(f)
    print(f"\n{'='*60}")
    print("Meta info:")
    print(f"  odds_enriched_count: {meta.get('odds_enriched_count')}")
    print(f"  theoddsapi_matches: {meta.get('theoddsapi_matches')}")
else:
    print("\nvip_bets_day_meta.json not found")
