"""
scripts/generate_dashboard_data.py

Generate static JSON files for the dashboard (no Flask API needed).
Runs via GitHub Actions daily.
"""

import json
import os
import sys
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.roi_tracker import ROITracker


def generate_all_data():
    """Generate all dashboard JSON files."""
    
    output_dir = os.path.join("dashboard", "public", "data")
    os.makedirs(output_dir, exist_ok=True)
    
    tracker = ROITracker()
    
    # 1. Overall stats (7 days)
    stats_7d = tracker.get_stats(days=7)
    with open(os.path.join(output_dir, "stats_7d.json"), "w") as f:
        json.dump(stats_7d, f, indent=2)
    
    # 2. VIP stats (7 days)
    vip_7d = tracker.get_stats(days=7, tier="VIP")
    with open(os.path.join(output_dir, "vip_7d.json"), "w") as f:
        json.dump(vip_7d, f, indent=2)
    
    # 3. FREE stats (7 days)
    free_7d = tracker.get_stats(days=7, tier="FREE")
    with open(os.path.join(output_dir, "free_7d.json"), "w") as f:
        json.dump(free_7d, f, indent=2)
    
    # 4. Top wins
    top_wins = tracker.get_top_wins(days=7, limit=3)
    with open(os.path.join(output_dir, "top_wins.json"), "w") as f:
        json.dump(top_wins, f, indent=2)
    
    # 5. ROI trend data (5, 10, 15, 20, 25, 30 days)
    trend_data = []
    for days in [5, 10, 15, 20, 25, 30]:
        stats = tracker.get_stats(days=days)
        trend_data.append({
            "days": days,
            "roi": stats.get("roi", 0),
            "hit_rate": stats.get("hit_rate", 0),
        })
    
    with open(os.path.join(output_dir, "roi_trend.json"), "w") as f:
        json.dump(trend_data, f, indent=2)
    
    # 6. Recent bets
    import sqlite3
    
    db_path = os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))
    
    recent_bets = []
    
    if os.path.exists(db_path):
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        
        rows = con.execute("""
            SELECT
                b.id,
                b.tier,
                b.home_team,
                b.away_team,
                b.league_name,
                b.tip,
                b.confidence,
                b.risk_level,
                b.odds_pick,
                b.kickoff_local,
                r.result_1x2,
                r.final_score
            FROM bets b
            LEFT JOIN results r ON b.fixture_id = r.fixture_id
            JOIN runs ru ON b.run_id = ru.id
            ORDER BY b.kickoff_local DESC
            LIMIT 20
        """).fetchall()
        
        con.close()
        
        for row in rows:
            # Determine outcome
            outcome = None
            if row['result_1x2']:
                tip_lower = (row['tip'] or '').lower()
                result = row['result_1x2']
                
                if ('hazai' in tip_lower or 'home' in tip_lower) and result == '1':
                    outcome = 'won'
                elif ('döntetlen' in tip_lower or 'draw' in tip_lower) and result == 'X':
                    outcome = 'won'
                elif ('vendég' in tip_lower or 'away' in tip_lower) and result == '2':
                    outcome = 'won'
                else:
                    outcome = 'lost'
            else:
                outcome = 'pending'
            
            recent_bets.append({
                'id': row['id'],
                'tier': row['tier'],
                'match': f"{row['home_team']} vs {row['away_team']}",
                'league': row['league_name'],
                'tip': row['tip'],
                'confidence': row['confidence'],
                'risk': row['risk_level'],
                'odds': row['odds_pick'],
                'kickoff': row['kickoff_local'],
                'result': row['final_score'],
                'outcome': outcome,
            })
    
    with open(os.path.join(output_dir, "recent_bets.json"), "w") as f:
        json.dump(recent_bets, f, indent=2)
    
    # 7. Metadata (last updated)
    metadata = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_stats": len(recent_bets),
    }
    
    with open(os.path.join(output_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✅ Generated dashboard data:")
    print(f"   - Overall: {stats_7d.get('total_bets')} bets, {stats_7d.get('roi')}% ROI")
    print(f"   - VIP: {vip_7d.get('total_bets')} bets, {vip_7d.get('roi')}% ROI")
    print(f"   - FREE: {free_7d.get('total_bets')} bets, {free_7d.get('roi')}% ROI")
    print(f"   - Top wins: {len(top_wins)}")
    print(f"   - Recent bets: {len(recent_bets)}")
    print(f"   - Output: {output_dir}")


if __name__ == "__main__":
    generate_all_data()
