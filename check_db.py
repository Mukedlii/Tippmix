import sqlite3
import os

db_path = 'data/tippmix.db'
if not os.path.exists(db_path):
    print(f"ERROR: DB does not exist: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

print("Tables:")
tables = [x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(tables)

if 'bets' in tables:
    print("\nLast 10 bets:")
    cols = [d[0] for d in c.execute("SELECT * FROM bets LIMIT 1").description]
    print(f"Columns: {cols}")
    
    for row in c.execute("SELECT * FROM bets ORDER BY rowid DESC LIMIT 10").fetchall():
        print(row)
        
    print("\nStats:")
    stats = c.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN result='won' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result='lost' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END) as pending
        FROM bets
    """).fetchone()
    print(f"Total: {stats[0]}, Wins: {stats[1]}, Losses: {stats[2]}, Pending: {stats[3]}")
    if stats[0] > 0 and stats[1] is not None:
        print(f"Win rate: {stats[1]/(stats[0]-stats[3] if stats[3] else stats[0])*100:.1f}%")
else:
    print("ERROR: 'bets' table does not exist")

conn.close()
