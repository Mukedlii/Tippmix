#!/usr/bin/env python3
"""
Phase 4 - AI Consensus Analysis
Analyze tipster picks using OpenAI GPT-4o-mini and select TOP 6 matches
"""

import os
import sys
import io
import json
from datetime import datetime
from collections import defaultdict

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.storage.tipster_tracking import get_db, save_ai_consensus


def get_todays_tips_grouped():
    """
    Get today's unsettled tips, grouped by match
    Include tipster quality stats
    """
    
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    c.execute("""
        SELECT 
            tt.id, tt.match_date, tt.home_team, tt.away_team,
            tt.selection, tt.odds, tt.confidence, tt.raw_text,
            t.name as tipster_name, t.total_settled, t.total_won,
            t.win_rate, t.avg_roi, t.is_qualified
        FROM tipster_tips tt
        JOIN tipsters t ON tt.tipster_id = t.id
        WHERE tt.match_date >= ?
        AND tt.is_settled = 0
        ORDER BY tt.home_team, tt.away_team, tt.selection
    """, (today,))
    
    tips = [dict(row) for row in c.fetchall()]
    conn.close()
    
    # Group by match + selection
    grouped = defaultdict(list)
    
    for tip in tips:
        match_key = f"{tip['home_team']} vs {tip['away_team']}"
        selection_key = f"{match_key}|{tip['selection']}"
        grouped[selection_key].append(tip)
    
    return grouped


def calculate_consensus_strength(tips):
    """
    Calculate consensus strength for a group of tips
    
    Returns:
        Dict with consensus metrics
    """
    
    total_tipsters = len(tips)
    qualified_tipsters = [t for t in tips if t['is_qualified']]
    qualified_count = len(qualified_tipsters)
    
    # Average stats
    avg_win_rate = sum([t['win_rate'] or 0 for t in tips if t['win_rate']]) / max(total_tipsters, 1)
    avg_roi = sum([t['avg_roi'] or 0 for t in tips if t['avg_roi']]) / max(total_tipsters, 1)
    
    # Qualified average (if any)
    if qualified_count > 0:
        qualified_win_rate = sum([t['win_rate'] or 0 for t in qualified_tipsters]) / qualified_count
        qualified_roi = sum([t['avg_roi'] or 0 for t in qualified_tipsters]) / qualified_count
    else:
        qualified_win_rate = 0
        qualified_roi = 0
    
    # Consensus strength (0-100)
    # Factors:
    # - Number of qualified tipsters (more = better)
    # - Qualified win rate (higher = better)
    # - Qualified ROI (higher = better)
    
    strength = 0
    
    # +30 for each qualified tipster (max 90 for 3+)
    strength += min(qualified_count * 30, 90)
    
    # +10 for high qualified win rate (>60%)
    if qualified_win_rate > 0.60:
        strength += 10
    
    # +10 for high qualified ROI (>10%)
    if qualified_roi > 0.10:
        strength += 10
    
    # -20 if no qualified tipsters
    if qualified_count == 0:
        strength = max(strength - 20, 0)
    
    strength = min(strength, 100)
    
    return {
        'total_tipsters': total_tipsters,
        'qualified_count': qualified_count,
        'avg_win_rate': avg_win_rate,
        'avg_roi': avg_roi,
        'qualified_win_rate': qualified_win_rate,
        'qualified_roi': qualified_roi,
        'consensus_strength': strength / 100.0  # 0-1 scale
    }


def analyze_with_ai(match_data):
    """
    Send match data to OpenAI for AI analysis
    
    Args:
        match_data: List of matches with consensus data
    
    Returns:
        AI recommendations (TOP 6 matches)
    """
    
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("⚠️  OPENAI_API_KEY not set! Skipping AI analysis.")
        print("   Using simple consensus ranking instead.\n")
        
        # Fallback: sort by consensus strength
        sorted_matches = sorted(
            match_data,
            key=lambda x: (x['consensus']['qualified_count'], x['consensus']['consensus_strength']),
            reverse=True
        )
        
        return sorted_matches[:6]
    
    # Prepare prompt
    prompt = """You are a sports betting expert analyzing tipster consensus data.

Your task: Select the TOP 6 most reliable picks from today's tipster recommendations.

CRITERIA:
1. **Qualified Tipster Agreement** - Picks backed by multiple QUALIFIED tipsters (win_rate >= 55%, ROI >= 5%, sample >= 20 tips)
2. **Historical Performance** - Qualified tipsters' avg win rate and ROI
3. **Consensus Strength** - How many tipsters agree on this pick
4. **Odds Value** - Odds in sweet spot (1.50-2.50 = good value, avoid <1.30 or >4.00)
5. **Risk Balance** - Mix of safer picks (1.50-1.80) and value picks (1.80-2.50)

TODAY'S DATA:
"""
    
    # Add match data to prompt
    for i, match in enumerate(match_data, 1):
        consensus = match['consensus']
        tips = match['tips']
        
        prompt += f"\n{i}. {match['match_key']}\n"
        prompt += f"   Selection: {match['selection']}\n"
        prompt += f"   Tipsters: {consensus['total_tipsters']} total, {consensus['qualified_count']} qualified\n"
        
        if consensus['qualified_count'] > 0:
            prompt += f"   Qualified Stats: {consensus['qualified_win_rate']*100:.1f}% win rate, {consensus['qualified_roi']*100:+.1f}% ROI\n"
        else:
            prompt += f"   Average Stats: {consensus['avg_win_rate']*100:.1f}% win rate, {consensus['avg_roi']*100:+.1f}% ROI\n"
        
        prompt += f"   Consensus Strength: {consensus['consensus_strength']*100:.0f}/100\n"
        
        # Sample odds (average from tipsters)
        odds_list = [t['odds'] for t in tips if t['odds'] and t['odds'] > 0]
        if odds_list:
            avg_odds = sum(odds_list) / len(odds_list)
            prompt += f"   Average Odds: {avg_odds:.2f}\n"
        
        # Qualified tipster names
        qualified_names = [t['tipster_name'] for t in tips if t['is_qualified']]
        if qualified_names:
            prompt += f"   Qualified Tipsters: {', '.join(qualified_names)}\n"
    
    prompt += """
RESPONSE FORMAT (JSON):
{
  "top_6": [
    {
      "rank": 1,
      "match": "Team A vs Team B",
      "selection": "Home Win",
      "ai_confidence": 0.85,
      "reasoning": "3 qualified tipsters agree (avg 65% win rate, +12% ROI). Odds 1.75 offer good value."
    },
    ...
  ]
}

Select the TOP 6 picks with highest confidence. Provide short reasoning for each.
"""
    
    # Call OpenAI API
    try:
        import openai
        
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a sports betting analyst expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Map AI results back to match_data
        top_6 = []
        for ai_pick in result.get('top_6', [])[:6]:
            # Find matching original match
            for match in match_data:
                if match['match_key'] in ai_pick['match'] and match['selection'] in ai_pick['selection']:
                    top_6.append({
                        **match,
                        'ai_confidence': ai_pick['ai_confidence'],
                        'ai_reasoning': ai_pick['reasoning'],
                        'rank': ai_pick['rank']
                    })
                    break
        
        return top_6
    
    except Exception as e:
        print(f"❌ OpenAI API error: {e}")
        print("   Falling back to simple consensus ranking.\n")
        
        # Fallback
        sorted_matches = sorted(
            match_data,
            key=lambda x: (x['consensus']['qualified_count'], x['consensus']['consensus_strength']),
            reverse=True
        )
        
        return sorted_matches[:6]


def main():
    print("\n" + "="*60)
    print(f"🤖 AI CONSENSUS ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60 + "\n")
    
    # Get today's tips
    print("📊 Loading today's tips...\n")
    grouped_tips = get_todays_tips_grouped()
    
    if not grouped_tips:
        print("⚠️  No unsettled tips found for today\n")
        return
    
    print(f"✅ Found {len(grouped_tips)} unique match+selection combinations\n")
    
    # Calculate consensus for each
    print("🔍 Calculating consensus strength...\n")
    
    match_data = []
    
    for key, tips in grouped_tips.items():
        match_key, selection = key.split('|', 1)
        consensus = calculate_consensus_strength(tips)
        
        match_data.append({
            'match_key': match_key,
            'selection': selection,
            'tips': tips,
            'consensus': consensus
        })
        
        print(f"  {match_key}")
        print(f"    {selection}: {consensus['total_tipsters']} tipsters ({consensus['qualified_count']} qualified) - Strength: {consensus['consensus_strength']*100:.0f}/100")
    
    print()
    
    # Filter: at least 2 tipsters OR 1 qualified
    filtered = [m for m in match_data if m['consensus']['total_tipsters'] >= 2 or m['consensus']['qualified_count'] >= 1]
    
    print(f"✅ {len(filtered)} picks meet minimum criteria (2+ tipsters OR 1+ qualified)\n")
    
    if not filtered:
        print("⚠️  No picks meet criteria for AI analysis\n")
        return
    
    # AI Analysis
    print("🤖 Running AI analysis...\n")
    top_6 = analyze_with_ai(filtered)
    
    # Display results
    print(f"\n{'='*60}")
    print("🎯 TOP 6 AI CONSENSUS PICKS")
    print("="*60 + "\n")
    
    for i, pick in enumerate(top_6, 1):
        print(f"{i}. {pick['match_key']}")
        print(f"   Selection: {pick['selection']}")
        print(f"   Tipsters: {pick['consensus']['total_tipsters']} ({pick['consensus']['qualified_count']} qualified)")
        print(f"   Consensus: {pick['consensus']['consensus_strength']*100:.0f}/100")
        
        if pick.get('ai_confidence'):
            print(f"   AI Confidence: {pick['ai_confidence']*100:.0f}%")
        if pick.get('ai_reasoning'):
            print(f"   Reasoning: {pick['ai_reasoning']}")
        
        print()
    
    # Save to DB
    print("💾 Saving AI consensus to database...\n")
    
    for i, pick in enumerate(top_6, 1):
        sample_tip = pick['tips'][0]
        
        save_ai_consensus(
            match_date=sample_tip['match_date'],
            home_team=sample_tip['home_team'],
            away_team=sample_tip['away_team'],
            selection=pick['selection'],
            ai_confidence=pick.get('ai_confidence', pick['consensus']['consensus_strength']),
            tipster_count=pick['consensus']['total_tipsters'],
            qualified_tipster_count=pick['consensus']['qualified_count'],
            avg_tipster_roi=pick['consensus']['avg_roi'],
            avg_tipster_winrate=pick['consensus']['avg_win_rate'],
            consensus_strength=pick['consensus']['consensus_strength'],
            ai_reasoning=pick.get('ai_reasoning', 'Consensus-based selection'),
            is_top6=True,
            rank_position=i
        )
    
    print(f"✅ Saved {len(top_6)} TOP 6 picks to database\n")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
