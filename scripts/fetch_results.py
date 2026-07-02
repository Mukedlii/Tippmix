#!/usr/bin/env python3
"""
Phase 3 - Result Fetching
Fetch match results from TheOddsAPI and save to DB
"""

import os
import sys
import io
import requests
from datetime import datetime, timedelta

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.storage.tipster_tracking import get_db


def fetch_completed_matches(days_back=1):
    """
    Fetch completed match results from TheOddsAPI
    
    Args:
        days_back: How many days back to check for completed matches
    
    Returns:
        List of match results
    """
    
    api_key = os.getenv('ODDS_API_KEY', '<your_odds_api_key>')
    
    results = []
    sports = ['soccer_epl', 'soccer_spain_la_liga', 'soccer_germany_bundesliga', 
              'soccer_italy_serie_a', 'soccer_france_ligue_one']
    
    for sport in sports:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores/"
        
        params = {
            'apiKey': api_key,
            'daysFrom': days_back,
            'dateFormat': 'iso'
        }
        
        try:
            print(f"📊 Fetching {sport} results...")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                for match in data:
                    if match.get('completed'):
                        results.append({
                            'sport': sport,
                            'home_team': match.get('home_team'),
                            'away_team': match.get('away_team'),
                            'commence_time': match.get('commence_time'),
                            'completed': match.get('completed'),
                            'scores': match.get('scores', []),
                            'last_update': match.get('last_update')
                        })
                
                print(f"  ✅ {len([m for m in data if m.get('completed')])} completed matches")
            else:
                print(f"  ❌ HTTP {response.status_code}")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    return results


def save_results_to_db(results):
    """
    Save match results to database
    Create results table if needed
    """
    
    conn = get_db()
    c = conn.cursor()
    
    # Create results table if not exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY,
            match_date TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_score INTEGER,
            away_score INTEGER,
            sport TEXT,
            source TEXT DEFAULT 'theoddsapi',
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(match_date, home_team, away_team)
        )
    """)
    
    saved_count = 0
    
    for result in results:
        try:
            # Parse scores
            scores = result.get('scores', [])
            home_score = None
            away_score = None
            
            if len(scores) >= 2:
                for score in scores:
                    if score.get('name') == result['home_team']:
                        home_score = score.get('score')
                    elif score.get('name') == result['away_team']:
                        away_score = score.get('score')
            
            # Parse date
            commence_time = result.get('commence_time', '')
            match_date = commence_time.split('T')[0] if 'T' in commence_time else None
            
            if not match_date:
                continue
            
            # Insert or ignore if duplicate
            c.execute("""
                INSERT OR IGNORE INTO match_results 
                (match_date, home_team, away_team, home_score, away_score, sport)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                match_date,
                result['home_team'],
                result['away_team'],
                home_score,
                away_score,
                result['sport']
            ))
            
            if c.rowcount > 0:
                saved_count += 1
                print(f"  ✅ {result['home_team']} {home_score}-{away_score} {result['away_team']}")
        
        except Exception as e:
            print(f"  ⚠️  Error saving result: {e}")
    
    conn.commit()
    conn.close()
    
    return saved_count


def main():
    print("\n" + "="*60)
    print(f"🏆 RESULT FETCHER - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60 + "\n")
    
    # Fetch results
    print("📥 Fetching match results from TheOddsAPI...\n")
    results = fetch_completed_matches(days_back=3)
    
    print(f"\n✅ Total completed matches found: {len(results)}\n")
    
    if results:
        # Save to DB
        print("💾 Saving results to database...\n")
        saved = save_results_to_db(results)
        
        print(f"\n{'='*60}")
        print(f"✅ SAVED: {saved} new results")
        print("="*60 + "\n")
    else:
        print("\n⚠️  No results found\n")


if __name__ == '__main__':
    main()
