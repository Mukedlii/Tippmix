#!/usr/bin/env python3
"""
Reddit Tipster Aggregator

Scrapes r/SoccerBetting daily picks threads and builds consensus.
Free data source - no API key needed (uses public JSON endpoint).
"""

import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests


def get_daily_picks_thread() -> Optional[str]:
    """
    Find today's Daily Picks Thread on r/SoccerBetting
    
    Returns:
        Thread URL or None
    """
    
    subreddit_url = "https://www.reddit.com/r/SoccerBetting/new.json"
    headers = {"User-Agent": "Tippmix/1.0"}
    
    try:
        resp = requests.get(subreddit_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        posts = data.get('data', {}).get('children', [])
        
        # Look for "Daily Picks Thread" from today or yesterday
        today = datetime.now().strftime("%B %d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d")
        
        for post in posts:
            post_data = post.get('data', {})
            title = post_data.get('title', '')
            
            if 'daily picks thread' in title.lower():
                if today in title or yesterday in title:
                    return "https://www.reddit.com" + post_data.get('permalink', '')
        
        return None
        
    except Exception as e:
        print(f"Error fetching Reddit: {e}")
        return None


def parse_tipster_comments(thread_url: str) -> List[Dict]:
    """
    Parse comments from Daily Picks Thread
    
    Returns:
        List of picks with format:
        {
            "match": str,
            "pick": str,  # e.g., "Home Win", "Over 2.5", "BTTS Yes"
            "odds": float or None,
            "confidence": int,  # upvotes
            "tipster": str
        }
    """
    
    if not thread_url:
        return []
    
    json_url = thread_url.rstrip('/') + '.json'
    headers = {"User-Agent": "Tippmix/1.0"}
    
    try:
        time.sleep(2)  # Reddit rate limit
        resp = requests.get(json_url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        
        # Reddit structure: [post_data, comments_data]
        if len(data) < 2:
            return []
        
        comments_data = data[1].get('data', {}).get('children', [])
        
        picks = []
        
        for comment_obj in comments_data:
            comment_data = comment_obj.get('data', {})
            
            # Skip deleted/removed
            if comment_data.get('author') in ['[deleted]', 'AutoModerator']:
                continue
            
            body = comment_data.get('body', '')
            score = comment_data.get('score', 0)
            author = comment_data.get('author', 'unknown')
            
            # Simple pick detection (can be improved)
            # Look for patterns like:
            # - Team A vs Team B - Home Win @1.80
            # - Arsenal ML
            # - Over 2.5 goals
            
            lines = body.split('\n')
            for line in lines:
                line = line.strip()
                
                # Skip if too short or no hyphen/@ symbol
                if len(line) < 10 or ('-' not in line and '@' not in line):
                    continue
                
                # Try to extract: match, pick, odds
                match_pick = None
                odds_value = None
                
                # Pattern: "Team A vs Team B - Pick @odds"
                if ' vs ' in line or ' v ' in line:
                    match_pick = line
                    
                    # Extract odds if present
                    odds_match = re.search(r'@(\d+\.?\d*)', line)
                    if odds_match:
                        try:
                            odds_value = float(odds_match.group(1))
                        except ValueError:
                            pass
                
                elif any(keyword in line.lower() for keyword in ['btts', 'over', 'under', 'ml', 'win', 'draw']):
                    match_pick = line
                    odds_match = re.search(r'@(\d+\.?\d*)', line)
                    if odds_match:
                        try:
                            odds_value = float(odds_match.group(1))
                        except ValueError:
                            pass
                
                if match_pick:
                    picks.append({
                        "match": match_pick,
                        "pick": match_pick,  # Can be refined
                        "odds": odds_value,
                        "confidence": max(score, 1),  # Min 1
                        "tipster": author
                    })
        
        return picks
        
    except Exception as e:
        print(f"Error parsing Reddit comments: {e}")
        return []


def build_consensus(picks: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Build consensus from all picks
    
    Groups by match/pick and calculates:
    - Total tipsters
    - Average confidence (upvotes)
    - Odds range
    
    Returns:
        {
            "match_name": [
                {
                    "pick": str,
                    "tipsters": int,
                    "avg_confidence": float,
                    "avg_odds": float,
                    "consensus_strength": float  # 0-1
                }
            ]
        }
    """
    
    from collections import defaultdict
    
    grouped = defaultdict(list)
    
    # Simple grouping (can be improved with fuzzy matching)
    for pick in picks:
        key = pick['match'].lower()[:50]  # First 50 chars as key
        grouped[key].append(pick)
    
    consensus = {}
    
    for match_key, match_picks in grouped.items():
        if len(match_picks) < 2:  # Need at least 2 tipsters
            continue
        
        # Calculate stats
        total_tipsters = len(match_picks)
        avg_conf = sum(p['confidence'] for p in match_picks) / total_tipsters
        
        odds_values = [p['odds'] for p in match_picks if p['odds']]
        avg_odds = sum(odds_values) / len(odds_values) if odds_values else None
        
        # Consensus strength (higher confidence + more tipsters = stronger)
        strength = min((total_tipsters / 10.0) * (avg_conf / 5.0), 1.0)
        
        # Determine dominant pick
        pick_counts = {}
        for p in match_picks:
            pick_lower = p['pick'].lower()
            pick_counts[pick_lower] = pick_counts.get(pick_lower, 0) + 1
        
        dominant_pick = max(pick_counts, key=pick_counts.get) if pick_counts else match_key
        
        consensus[match_key] = [{
            "pick": dominant_pick,
            "tipsters": total_tipsters,
            "avg_confidence": round(avg_conf, 1),
            "avg_odds": round(avg_odds, 2) if avg_odds else None,
            "consensus_strength": round(strength, 2)
        }]
    
    return consensus


def format_reddit_summary(consensus: Dict, top_n: int = 10) -> str:
    """Format consensus for Telegram"""
    
    if not consensus:
        return "No Reddit consensus found for today."
    
    # Sort by consensus strength
    sorted_picks = sorted(
        [(k, v[0]) for k, v in consensus.items()],
        key=lambda x: x[1]['consensus_strength'],
        reverse=True
    )
    
    lines = [f"REDDIT CONSENSUS (r/SoccerBetting) - Top {top_n}:"]
    lines.append("=" * 50)
    
    for idx, (match, data) in enumerate(sorted_picks[:top_n], 1):
        tipsters = data['tipsters']
        conf = data['avg_confidence']
        odds = data['avg_odds']
        strength = data['consensus_strength']
        
        odds_str = f"@{odds}" if odds else "TBA"
        strength_icon = "STRONG" if strength > 0.7 else "MODERATE" if strength > 0.4 else "WEAK"
        
        lines.append(f"{idx}. [{strength_icon}] {match[:60]}")
        lines.append(f"   {tipsters} tipsters | Avg conf: {conf} | Odds: {odds_str}")
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("Fetching Reddit Daily Picks Thread...\n")
    
    thread_url = get_daily_picks_thread()
    
    if not thread_url:
        print("Could not find today's Daily Picks Thread")
    else:
        print(f"Found thread: {thread_url}\n")
        print("Parsing comments...")
        
        picks = parse_tipster_comments(thread_url)
        print(f"Found {len(picks)} picks\n")
        
        if picks:
            consensus = build_consensus(picks)
            print(format_reddit_summary(consensus, top_n=15))
