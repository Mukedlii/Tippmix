#!/usr/bin/env python3
import sqlite3
import json

con = sqlite3.connect('data/tippmix.db')
run_id = con.execute('SELECT MAX(id) FROM runs').fetchone()[0]

print(f"\n{'='*60}")
print(f"LAST RUN: {run_id}")
print(f"{'='*60}")

# Count by tier
counts = con.execute('SELECT tier, COUNT(*) FROM bets WHERE run_id=? GROUP BY tier', (run_id,)).fetchall()
print("\nBets by tier:")
for tier, count in counts:
    print(f"  {tier}: {count}")

# VIP data quality
print("\n" + "="*60)
print("VIP BETS DATA QUALITY:")
print("="*60)

vip_bets = con.execute('SELECT raw_json FROM bets WHERE run_id=? AND tier="VIP"', (run_id,)).fetchall()

for i, (raw,) in enumerate(vip_bets, 1):
    data = json.loads(raw)
    dq = data.get('data_quality', 'N/A')
    n_home = data.get('n_home', 0)
    n_away = data.get('n_away', 0)
    n_league = data.get('n_league', 0)
    used_team_defaults = data.get('used_team_defaults', False)
    used_league_defaults = data.get('used_league_defaults', False)
    home = data.get('home_team', 'N/A')
    away = data.get('away_team', 'N/A')
    pick = data.get('tip', 'N/A')
    
    print(f"\n#{i}: {home} vs {away}")
    print(f"  Pick: {pick}")
    print(f"  Data quality: {dq}")
    print(f"  Historical matches: home={n_home}, away={n_away}, league={n_league}")
    print(f"  Used defaults: team={used_team_defaults}, league={used_league_defaults}")

con.close()
