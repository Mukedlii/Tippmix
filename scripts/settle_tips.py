#!/usr/bin/env python3
"""
Phase 3 - Tip Settlement
Match tips with results and settle them (won/lost)
"""

import os
import sys
import io
from datetime import datetime

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.storage.tipster_tracking import get_db, settle_tip


def normalize_team_name(team):
    """Normalize team name for matching"""
    if not team:
        return ""
    
    # Lowercase, strip whitespace
    team = team.lower().strip()
    
    # Common substitutions
    replacements = {
        'fc': '',
        'afc': '',
        'cf': '',
        'united': 'utd',
        'manchester': 'man',
        'tottenham': 'spurs',
        'hotspur': 'spurs'
    }
    
    for old, new in replacements.items():
        team = team.replace(old, new)
    
    # Remove extra spaces
    team = ' '.join(team.split())
    
    return team


def teams_match(team1, team2):
    """
    Check if two team names refer to the same team
    Simple version: normalized exact match
    """
    
    norm1 = normalize_team_name(team1)
    norm2 = normalize_team_name(team2)
    
    # Exact match
    if norm1 == norm2:
        return True
    
    # Contains match (e.g., "man city" in "manchester city")
    if norm1 in norm2 or norm2 in norm1:
        return True
    
    return False


def determine_result(selection, home_score, away_score):
    """
    Determine if a selection won based on the score
    
    Args:
        selection: Pick type (e.g., "Home Win", "Over 2.5", "BTTS")
        home_score: Home team score
        away_score: Away team score
    
    Returns:
        True if won, False if lost, None if can't determine
    """
    
    if home_score is None or away_score is None:
        return None
    
    selection_lower = selection.lower()
    total_goals = home_score + away_score
    
    # Home Win
    if 'home win' in selection_lower or 'home to win' in selection_lower:
        return home_score > away_score
    
    # Away Win
    if 'away win' in selection_lower or 'away to win' in selection_lower:
        return away_score > home_score
    
    # Draw
    if 'draw' in selection_lower and 'no' not in selection_lower:
        return home_score == away_score
    
    # BTTS (Both Teams To Score)
    if 'btts' in selection_lower or 'both teams to score' in selection_lower:
        if 'no' in selection_lower or 'btts no' in selection_lower:
            return home_score == 0 or away_score == 0
        else:
            return home_score > 0 and away_score > 0
    
    # Over/Under
    if 'over' in selection_lower:
        try:
            # Extract line (e.g., "Over 2.5")
            parts = selection_lower.split()
            for part in parts:
                try:
                    line = float(part)
                    return total_goals > line
                except:
                    continue
        except:
            pass
    
    if 'under' in selection_lower:
        try:
            parts = selection_lower.split()
            for part in parts:
                try:
                    line = float(part)
                    return total_goals < line
                except:
                    continue
        except:
            pass
    
    # Can't determine
    return None


def settle_pending_tips():
    """
    Match unsettled tips with results and settle them
    """
    
    conn = get_db()
    c = conn.cursor()
    
    # Get unsettled tips
    c.execute("""
        SELECT tt.id, tt.match_date, tt.home_team, tt.away_team, 
               tt.selection, t.name as tipster_name
        FROM tipster_tips tt
        JOIN tipsters t ON tt.tipster_id = t.id
        WHERE tt.is_settled = 0
        ORDER BY tt.match_date ASC
    """)
    
    unsettled_tips = [dict(row) for row in c.fetchall()]
    
    if not unsettled_tips:
        print("✅ No unsettled tips found\n")
        conn.close()
        return 0
    
    print(f"📋 Found {len(unsettled_tips)} unsettled tips\n")
    
    # Get all results
    c.execute("""
        SELECT match_date, home_team, away_team, home_score, away_score
        FROM match_results
    """)
    
    results = [dict(row) for row in c.fetchall()]
    print(f"📊 Found {len(results)} match results in DB\n")
    
    settled_count = 0
    
    for tip in unsettled_tips:
        # Find matching result
        matched_result = None
        
        for result in results:
            # Check date match
            if tip['match_date'] != result['match_date']:
                continue
            
            # Check team match
            if (teams_match(tip['home_team'], result['home_team']) and 
                teams_match(tip['away_team'], result['away_team'])):
                matched_result = result
                break
        
        if not matched_result:
            continue
        
        # Determine if won
        won = determine_result(
            tip['selection'],
            matched_result['home_score'],
            matched_result['away_score']
        )
        
        if won is None:
            print(f"  ⚠️  Can't determine: {tip['selection']} ({tip['home_team']} vs {tip['away_team']})")
            continue
        
        # Settle tip
        actual_score = f"{matched_result['home_score']}-{matched_result['away_score']}"
        settle_tip(tip['id'], won, actual_score)
        
        result_icon = "✅" if won else "❌"
        print(f"  {result_icon} {tip['tipster_name']}: {tip['selection']} - {actual_score}")
        
        settled_count += 1
    
    conn.close()
    
    return settled_count


def main():
    print("\n" + "="*60)
    print(f"⚖️  TIP SETTLER - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60 + "\n")
    
    settled = settle_pending_tips()
    
    print(f"\n{'='*60}")
    print(f"✅ SETTLED: {settled} tips")
    print("="*60 + "\n")
    
    # Show updated stats
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT name, total_settled, total_won, win_rate, avg_roi, is_qualified
        FROM tipsters
        WHERE total_settled > 0
        ORDER BY avg_roi DESC
    """)
    
    tipsters = [dict(row) for row in c.fetchall()]
    
    if tipsters:
        print("📊 UPDATED TIPSTER STATS:\n")
        for t in tipsters:
            qualified = "🏆" if t['is_qualified'] else "  "
            win_rate = f"{t['win_rate']*100:.1f}%" if t['win_rate'] else "N/A"
            avg_roi = f"{t['avg_roi']*100:+.1f}%" if t['avg_roi'] else "N/A"
            
            print(f"{qualified} {t['name']}: {t['total_won']}/{t['total_settled']} ({win_rate}) ROI: {avg_roi}")
        
        print()
    
    conn.close()


if __name__ == '__main__':
    main()
