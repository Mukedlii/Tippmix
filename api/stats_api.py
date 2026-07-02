"""
api/stats_api.py

Simple Flask API to serve stats for the Next.js dashboard.

Usage:
    python api/stats_api.py

Endpoints:
    GET /api/stats?days=7&tier=VIP
    GET /api/top-wins?days=7&limit=5
    GET /api/recent-bets?limit=20
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.roi_tracker import ROITracker
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


def _cors_origins() -> list[str]:
    raw = (os.getenv("TIPPMIX_API_CORS_ORIGINS") or "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    dashboard_url = (os.getenv("TIPPMIX_DASHBOARD_URL") or "").strip()
    defaults = [dashboard_url] if dashboard_url else []
    defaults.append("http://localhost:3000")
    return defaults


CORS(app, resources={r"/api/*": {"origins": _cors_origins()}})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get ROI statistics."""
    days = int(request.args.get('days', 7))
    tier = request.args.get('tier', None)
    
    tracker = ROITracker()
    stats = tracker.get_stats(days=days, tier=tier)
    
    return jsonify(stats)


@app.route('/api/top-wins', methods=['GET'])
def get_top_wins():
    """Get top winning bets."""
    days = int(request.args.get('days', 7))
    limit = int(request.args.get('limit', 5))
    
    tracker = ROITracker()
    wins = tracker.get_top_wins(days=days, limit=limit)
    
    return jsonify(wins)


@app.route('/api/recent-bets', methods=['GET'])
def get_recent_bets():
    """Get recent bets with results."""
    limit = int(request.args.get('limit', 20))
    tier = request.args.get('tier', None)
    
    import sqlite3
    from datetime import datetime, timedelta, timezone
    
    db_path = os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))
    
    if not os.path.exists(db_path):
        return jsonify([])
    
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    
    query = """
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
            r.final_score,
            r.home_goals,
            r.away_goals
        FROM bets b
        LEFT JOIN results r ON b.fixture_id = r.fixture_id
        JOIN runs ru ON b.run_id = ru.id
    """
    
    params = []
    
    if tier:
        query += " WHERE LOWER(b.tier) = LOWER(?)"
        params.append(tier)
    
    query += " ORDER BY b.kickoff_local DESC LIMIT ?"
    params.append(limit)
    
    rows = con.execute(query, params).fetchall()
    con.close()
    
    bets = []
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
        
        bets.append({
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
    
    return jsonify(bets)


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    port = int(os.getenv('API_PORT', 5000))
    debug = (os.getenv("FLASK_DEBUG") or "0").strip() == "1"
    app.run(host='0.0.0.0', port=port, debug=debug)
