import sqlite3
import os

db_path = 'data/tippmix.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== BETS (last 5) ===")
for row in c.execute("SELECT id, tier, home_team, away_team, tip, confidence, kickoff_local FROM bets ORDER BY id DESC LIMIT 5").fetchall():
    print(row)

print("\n=== RESULTS (all) ===")
cols_res = [d[0] for d in c.execute("SELECT * FROM results LIMIT 1").description]
print(f"Columns: {cols_res}")
for row in c.execute("SELECT * FROM results ORDER BY rowid DESC LIMIT 10").fetchall():
    print(row)

print("\n=== RUNS (last 5) ===")
for row in c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 5").fetchall():
    print(row)

conn.close()
