#!/usr/bin/env python3
"""
Reddit Tipster Aggregator

Scrapes r/SoccerBetting, r/SoccerPredictions, r/sportsbetting for daily picks.
Free data source - no API key needed (uses public JSON endpoint).
"""

import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests


def get_daily_picks_thread(subreddit: str = "SoccerBetting") -> Optional[str]:
    """
    Find today's Daily Picks Thread on r/SoccerBetting or similar subs
    
    Args:
        subreddit: Subreddit name (default: SoccerBetting)
    
    Returns:
        Thread URL or None
    """
    
    subreddit_url = f"https://www.reddit.com/r/{subreddit}/new.json"
    headers = {"User-Agent": "Tippmix/1.0"}
    
    try:
        resp = requests.get(subreddit_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"[Reddit] HTTP {resp.status_code} for r/{subreddit}")
            
            # Try alternative method if main fails
            try:
                from bot.providers.reddit_alternative import get_daily_picks_thread_alternative
                print(f"[Reddit] Trying alternative method for r/{subreddit}...")
                return get_daily_picks_thread_alternative(subreddit)
            except Exception as alt_e:
                print(f"[Reddit] Alternative method also failed: {alt_e}")
            
            return None
        
        data = resp.json()
        posts = data.get('data', {}).get('children', [])
        
        # Look for "Daily Picks Thread" with flexible matching
        now = datetime.now()
        
        # Multiple date formats to check
        date_formats = [
            now.strftime("%B %d"),           # "March 21"
            now.strftime("%d %B"),           # "21 March"
            now.strftime("%dst %B") if now.day in [1,21,31] else now.strftime("%dth %B"),  # "21st March"
            now.strftime("%dnd %B") if now.day in [2,22] else now.strftime("%dth %B"),      # "22nd March"
            now.strftime("%drd %B") if now.day in [3,23] else now.strftime("%dth %B"),      # "23rd March"
            (now - timedelta(days=1)).strftime("%B %d"),  # Yesterday
        ]
        
        # Flexible title patterns
        patterns = [
            'daily picks thread',
            'daily picks',
            'picks thread',
            'daily thread',
            'daily discussion',
        ]
        
        for post in posts:
            post_data = post.get('data', {})
            title = post_data.get('title', '')
            title_lower = title.lower()
            
            # Check if any pattern matches
            for pattern in patterns:
                if pattern in title_lower:
                    # Check date (any format OR "today")
                    if 'today' in title_lower or any(date_fmt.lower() in title_lower for date_fmt in date_formats):
                        permalink = post_data.get('permalink', '')
                        print(f"[Reddit] Found thread in r/{subreddit}: {title}")
                        return "https://www.reddit.com" + permalink
            
            # Fallback: any stickied post with "pick" or "thread" in title
            if post_data.get('stickied', False) and ('pick' in title or 'thread' in title):
                permalink = post_data.get('permalink', '')
                print(f"[Reddit] Found stickied thread in r/{subreddit}: {post_data.get('title')}")
                return "https://www.reddit.com" + permalink
        
        return None
        
    except Exception as e:
        print(f"[Reddit] Error fetching r/{subreddit}: {e}")
        return None


def get_all_picks_threads(subreddits: List[str] = None) -> Dict[str, Optional[str]]:
    """
    Find Daily Picks Threads from multiple subreddits
    
    Args:
        subreddits: List of subreddit names (default: SoccerBetting, SoccerPredictions, sportsbetting)
    
    Returns:
        Dict mapping subreddit → thread URL
    """
    if subreddits is None:
        subreddits = ["SoccerBetting", "SoccerPredictions", "sportsbetting"]
    
    threads = {}
    
    for sub in subreddits:
        thread = get_daily_picks_thread(sub)
        if thread:
            threads[sub] = thread
        time.sleep(2)  # Reddit rate limit
    
    return threads


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
            "tipster": str,
            "subreddit": str
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
        
        # Extract subreddit from URL
        subreddit = thread_url.split('/r/')[1].split('/')[0] if '/r/' in thread_url else 'unknown'
        
        for comment_obj in comments_data:
            comment_data = comment_obj.get('data', {})
            
            # Skip deleted/removed
            if comment_data.get('author') in ['[deleted]', 'AutoModerator']:
                continue
            
            body = comment_data.get('body', '')
            score = comment_data.get('score', 0)
            author = comment_data.get('author', 'anonymous')
            
            # Simple pattern matching for picks
            # Format: "Team A vs Team B - Home Win @ 2.50"
            # Format: "Arsenal - Win @ 1.80"
            # Format: "Chelsea vs Man United BTTS @ 1.90"
            
            lines = body.split('\n')
            
            for line in lines:
                line = line.strip()
                
                # Skip empty or very short lines
                if len(line) < 10:
                    continue
                
                # Look for common betting patterns
                if any(marker in line.lower() for marker in ['@', 'odds:', 'pick:', 'bet:', '->']):
                    
                    # Try to extract match name
                    match = None
                    pick = None
                    odds = None
                    
                    # Pattern: "Team A vs Team B"
                    vs_match = re.search(r'([A-Za-z\s\.\-]+)\s+vs\.?\s+([A-Za-z\s\.\-]+)', line, re.IGNORECASE)
                    if vs_match:
                        match = f"{vs_match.group(1).strip()} vs {vs_match.group(2).strip()}"
                    
                    # Pattern: odds (@ X.XX or odds: X.XX)
                    odds_match = re.search(r'[@:]?\s*(\d+\.\d{1,2})', line)
                    if odds_match:
                        try:
                            odds = float(odds_match.group(1))
                        except:
                            pass
                    
                    # Try to identify pick type
                    line_lower = line.lower()
                    if any(w in line_lower for w in ['win', 'victory', '1', 'home']):
                        pick = "Home Win"
                    elif any(w in line_lower for w in ['draw', 'x', 'tie']):
                        pick = "Draw"
                    elif any(w in line_lower for w in ['away', '2']):
                        pick = "Away Win"
                    elif 'btts' in line_lower or 'both teams' in line_lower:
                        pick = "BTTS Yes"
                    elif 'over' in line_lower:
                        over_match = re.search(r'over\s+(\d+\.?\d*)', line_lower)
                        if over_match:
                            pick = f"Over {over_match.group(1)}"
                        else:
                            pick = "Over 2.5"
                    elif 'under' in line_lower:
                        under_match = re.search(r'under\s+(\d+\.?\d*)', line_lower)
                        if under_match:
                            pick = f"Under {under_match.group(1)}"
                        else:
                            pick = "Under 2.5"
                    
                    # If we found a match OR pick with odds, add it
                    if (match or pick) and odds:
                        picks.append({
                            "match": match or line[:50],  # fallback to line excerpt
                            "pick": pick or "Unknown",
                            "odds": odds,
                            "confidence": score,
                            "tipster": author,
                            "subreddit": subreddit,
                            "raw_line": line
                        })
        
        return picks
        
    except Exception as e:
        print(f"[Reddit] Error parsing thread {thread_url}: {e}")
        return []


def build_consensus(picks: List[Dict], min_tipsters: int = 2) -> List[Dict]:
    """
    Build consensus from multiple tipster picks
    
    Args:
        picks: List of individual picks
        min_tipsters: Minimum number of tipsters needed for consensus
    
    Returns:
        List of consensus picks sorted by strength
    """
    
    # Group by match
    by_match = {}
    
    for pick in picks:
        match = pick.get('match', '').lower().strip()
        if not match or len(match) < 5:
            continue
        
        if match not in by_match:
            by_match[match] = []
        
        by_match[match].append(pick)
    
    consensus = []
    
    for match, match_picks in by_match.items():
        # Need at least min_tipsters
        if len(match_picks) < min_tipsters:
            continue
        
        # Group by pick type
        by_pick_type = {}
        for p in match_picks:
            pick_type = p.get('pick', '')
            if pick_type not in by_pick_type:
                by_pick_type[pick_type] = []
            by_pick_type[pick_type].append(p)
        
        # Find most popular pick
        for pick_type, pick_group in by_pick_type.items():
            if len(pick_group) >= min_tipsters:
                avg_odds = sum(p.get('odds', 0) for p in pick_group) / len(pick_group)
                total_confidence = sum(p.get('confidence', 0) for p in pick_group)
                
                consensus.append({
                    "match": match_picks[0].get('match'),  # original case
                    "pick": pick_type,
                    "tipster_count": len(pick_group),
                    "avg_odds": round(avg_odds, 2),
                    "total_upvotes": total_confidence,
                    "tipsters": [p.get('tipster') for p in pick_group],
                    "subreddits": list(set(p.get('subreddit') for p in pick_group))
                })
    
    # Sort by strength (tipster count * upvotes)
    consensus.sort(key=lambda x: x['tipster_count'] * (x['total_upvotes'] + 1), reverse=True)
    
    return consensus


def format_reddit_summary(consensus: List[Dict], top_n: int = 10) -> str:
    """
    Format consensus picks for Telegram
    """
    if not consensus:
        return "_No Reddit consensus found_"
    
    lines = [
        "🔥 *REDDIT CONSENSUS PICKS*",
        f"📊 {len(consensus)} matches with 2+ tipsters",
        "",
    ]
    
    for i, pick in enumerate(consensus[:top_n], 1):
        match = pick['match']
        pick_type = pick['pick']
        count = pick['tipster_count']
        odds = pick['avg_odds']
        upvotes = pick['total_upvotes']
        subs = ', '.join(f"r/{s}" for s in pick['subreddits'])
        
        lines.append(f"*{i}. {match}*")
        lines.append(f"   🎯 {pick_type} @ {odds}")
        lines.append(f"   👥 {count} tipsters | 👍 {upvotes} upvotes")
        lines.append(f"   📍 {subs}")
        lines.append("")
    
    lines.append("---")
    lines.append("_Forrás: Reddit r/SoccerBetting + r/SoccerPredictions + r/sportsbetting_")
    
    return "\n".join(lines)


def scrape_reddit_tipsters() -> List[Dict]:
    """
    Scrape all Reddit tipster picks
    
    Returns:
        List of picks with tipster, match, selection, odds, etc.
    """
    
    threads = get_all_picks_threads()
    
    all_picks = []
    for sub, thread_url in threads.items():
        if thread_url:
            picks = parse_tipster_comments(thread_url)
            # Add source subreddit to each pick
            for pick in picks:
                pick['source'] = f"r/{sub}"
            all_picks.extend(picks)
    
    return all_picks


if __name__ == "__main__":
    # Test
    print("Testing Reddit scraper...\n")
    
    threads = get_all_picks_threads()
    print(f"\nFound {len(threads)} threads:")
    for sub, url in threads.items():
        print(f"  r/{sub}: {url}")
    
    all_picks = []
    for sub, thread_url in threads.items():
        if thread_url:
            picks = parse_tipster_comments(thread_url)
            print(f"\nr/{sub}: {len(picks)} picks")
            all_picks.extend(picks)
    
    if all_picks:
        consensus = build_consensus(all_picks, min_tipsters=2)
        print(f"\n{len(consensus)} consensus picks\n")
        summary = format_reddit_summary(consensus)
        print(summary)
    else:
        print("\nNo picks found")
