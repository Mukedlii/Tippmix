#!/usr/bin/env python3
import sqlite3
import json

con = sqlite3.connect('data/tippmix.db')

print("Historical league IDs in DB:")
leagues = con.execute('SELECT DISTINCT league_id, raw_json FROM results WHERE league_id IS NOT NULL LIMIT 10').fetchall()

for lid, raw in leagues:
    data = json.loads(raw)
    league_name = data.get('league', {}).get('name', 'N/A')
    print(f"  ID {lid}: {league_name}")

print("\nCurrent match league IDs:")
bets = con.execute('SELECT DISTINCT raw_json FROM bets WHERE run_id=17 LIMIT 5').fetchall()

for (raw,) in bets:
    data = json.loads(raw)
    league_id = data.get('league_id')
    league_name = data.get('league_name', 'N/A')
    home = data.get('home_team')
    print(f"  {home}: league_id={league_id}, league_name={league_name}")

con.close()
