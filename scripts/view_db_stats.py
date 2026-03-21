#!/usr/bin/env python3
"""Quick DB stats viewer"""
import sys
import os
import io

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.storage.tipster_tracking import get_db

conn = get_db()
c = conn.cursor()

# Tipsters
c.execute('SELECT COUNT(*) FROM tipsters')
print(f"\n📊 Tipsters: {c.fetchone()[0]}")

c.execute('SELECT name, source, total_tips FROM tipsters ORDER BY total_tips DESC')
for row in c.fetchall():
    print(f"  - {row[0]} ({row[1]}): {row[2]} tips")

# Tips
c.execute('SELECT COUNT(*) FROM tipster_tips')
print(f"\n💡 Tips total: {c.fetchone()[0]}")

c.execute('''
    SELECT tt.home_team, tt.away_team, COUNT(*) as tip_count
    FROM tipster_tips tt
    GROUP BY tt.home_team, tt.away_team
    ORDER BY tip_count DESC
    LIMIT 10
''')
print("\n🔥 Most tipped matches:")
for row in c.fetchall():
    print(f"  - {row[0]} vs {row[1]}: {row[2]} tips")

conn.close()
