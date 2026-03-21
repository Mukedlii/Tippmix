#!/usr/bin/env python3
"""
BettingExpert.com Tipster Scraper

Scrapes public football tips from BettingExpert.com
Free data source - no API key needed (HTML scraping).
"""

import re
import time
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup


def scrape_football_tips(max_tips: int = 50) -> List[Dict]:
    """
    Scrape public football tips from BettingExpert.com
    
    Args:
        max_tips: Maximum number of tips to scrape
    
    Returns:
        List of tips with format:
        {
            "match": str,
            "pick": str,
            "odds": float,
            "tipster": str,
            "tipster_rating": str,  # e.g., "Expert", "Pro", etc.
            "confidence": int,      # yield (profit %)
            "source": "BettingExpert"
        }
    """
    
    url = "https://www.bettingexpert.com/tips/football"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        print(f"[BettingExpert] Fetching {url}...")
        resp = requests.get(url, headers=headers, timeout=20)
        
        if resp.status_code != 200:
            print(f"[BettingExpert] HTTP {resp.status_code}")
            return []
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        tips = []
        
        # BettingExpert uses various selectors - try multiple patterns
        # Pattern 1: tip cards/rows
        tip_elements = soup.find_all(['div', 'tr', 'article'], class_=re.compile(r'tip|pick|bet', re.I))
        
        if not tip_elements:
            # Fallback: find all links/elements containing team names vs pattern
            tip_elements = soup.find_all(text=re.compile(r'\w+\s+vs\.?\s+\w+', re.I))
            tip_elements = [el.parent for el in tip_elements if el.parent]
        
        print(f"[BettingExpert] Found {len(tip_elements)} potential tip elements")
        
        for elem in tip_elements[:max_tips * 3]:  # Over-fetch to compensate for parsing failures
            try:
                # Extract text content
                text = elem.get_text(separator=' ', strip=True)
                
                # Skip if too short
                if len(text) < 10:
                    continue
                
                # Look for match pattern: "Team A vs Team B"
                match_pattern = re.search(
                    r'([A-Za-z\s\.\-]+?)\s+vs\.?\s+([A-Za-z\s\.\-]+?)(?:\s|$)',
                    text,
                    re.IGNORECASE
                )
                
                if not match_pattern:
                    continue
                
                match = f"{match_pattern.group(1).strip()} vs {match_pattern.group(2).strip()}"
                
                # Extract odds
                odds_pattern = re.search(r'(\d+\.\d{1,2})', text)
                odds = float(odds_pattern.group(1)) if odds_pattern else None
                
                # Extract pick type
                pick = None
                text_lower = text.lower()
                
                if any(w in text_lower for w in ['home', 'win', '1', 'victory']):
                    pick = "Home Win"
                elif any(w in text_lower for w in ['draw', 'x', 'tie']):
                    pick = "Draw"
                elif any(w in text_lower for w in ['away', '2']):
                    pick = "Away Win"
                elif 'btts' in text_lower or 'both teams' in text_lower or 'both to score' in text_lower:
                    pick = "BTTS Yes"
                elif 'over' in text_lower:
                    over_match = re.search(r'over\s+(\d+\.?\d*)', text_lower)
                    pick = f"Over {over_match.group(1)}" if over_match else "Over 2.5"
                elif 'under' in text_lower:
                    under_match = re.search(r'under\s+(\d+\.?\d*)', text_lower)
                    pick = f"Under {under_match.group(1)}" if under_match else "Under 2.5"
                
                # Try to find tipster name
                tipster = None
                tipster_elem = elem.find(['span', 'div', 'a'], class_=re.compile(r'user|tipster|author', re.I))
                if tipster_elem:
                    tipster = tipster_elem.get_text(strip=True)
                
                # Try to find tipster rating/badge
                rating = None
                rating_elem = elem.find(['span', 'div', 'badge'], class_=re.compile(r'badge|rating|rank|expert|pro', re.I))
                if rating_elem:
                    rating = rating_elem.get_text(strip=True)
                
                # Try to find yield/profit
                yield_elem = elem.find(text=re.compile(r'yield|profit|%', re.I))
                confidence = 0
                if yield_elem:
                    yield_match = re.search(r'(\d+)%', str(yield_elem))
                    if yield_match:
                        confidence = int(yield_match.group(1))
                
                # Only add if we have match and odds
                if match and odds:
                    tips.append({
                        "match": match,
                        "pick": pick or "Unknown",
                        "odds": odds,
                        "tipster": tipster or "Anonymous",
                        "tipster_rating": rating or "",
                        "confidence": confidence,
                        "source": "BettingExpert",
                        "raw_text": text[:100]  # for debugging
                    })
                    
                    if len(tips) >= max_tips:
                        break
            
            except Exception as e:
                # Skip individual parsing errors
                continue
        
        print(f"[BettingExpert] Scraped {len(tips)} tips")
        return tips
    
    except Exception as e:
        print(f"[BettingExpert] Error: {e}")
        return []


def build_consensus_bettingexpert(tips: List[Dict], min_tips: int = 2) -> List[Dict]:
    """
    Build consensus from BettingExpert tips
    
    Args:
        tips: List of scraped tips
        min_tips: Minimum number of tips needed for consensus
    
    Returns:
        List of consensus picks sorted by strength
    """
    
    # Group by match
    by_match = {}
    
    for tip in tips:
        match = tip.get('match', '').lower().strip()
        if not match or len(match) < 5:
            continue
        
        if match not in by_match:
            by_match[match] = []
        
        by_match[match].append(tip)
    
    consensus = []
    
    for match, match_tips in by_match.items():
        # Group by pick type
        by_pick = {}
        
        for tip in match_tips:
            pick = tip.get('pick', 'Unknown')
            if pick not in by_pick:
                by_pick[pick] = []
            by_pick[pick].append(tip)
        
        # Find picks with min_tips
        for pick, pick_tips in by_pick.items():
            if len(pick_tips) >= min_tips:
                avg_odds = sum(t.get('odds', 0) for t in pick_tips) / len(pick_tips)
                avg_confidence = sum(t.get('confidence', 0) for t in pick_tips) / len(pick_tips)
                
                # Count expert tipsters
                expert_count = sum(1 for t in pick_tips if 'expert' in t.get('tipster_rating', '').lower() or 'pro' in t.get('tipster_rating', '').lower())
                
                consensus.append({
                    "match": match_tips[0].get('match'),  # original case
                    "pick": pick,
                    "tipster_count": len(pick_tips),
                    "expert_count": expert_count,
                    "avg_odds": round(avg_odds, 2),
                    "avg_confidence": round(avg_confidence, 1),
                    "tipsters": [t.get('tipster') for t in pick_tips],
                })
    
    # Sort by: expert count, then tipster count, then confidence
    consensus.sort(
        key=lambda x: (x['expert_count'], x['tipster_count'], x['avg_confidence']),
        reverse=True
    )
    
    return consensus


def format_bettingexpert_summary(consensus: List[Dict], top_n: int = 10) -> str:
    """
    Format BettingExpert consensus for Telegram
    """
    if not consensus:
        return "_No BettingExpert consensus found_"
    
    lines = [
        "⭐ *BETTINGEXPERT CONSENSUS*",
        f"📊 {len(consensus)} matches with 2+ tipsters",
        "",
    ]
    
    for i, pick in enumerate(consensus[:top_n], 1):
        match = pick['match']
        pick_type = pick['pick']
        count = pick['tipster_count']
        expert_count = pick['expert_count']
        odds = pick['avg_odds']
        conf = pick['avg_confidence']
        
        expert_mark = f" 👔 {expert_count} expert(s)" if expert_count > 0 else ""
        
        lines.append(f"*{i}. {match}*")
        lines.append(f"   🎯 {pick_type} @ {odds}")
        lines.append(f"   👥 {count} tipsters{expert_mark} | 📈 {conf}% avg yield")
        lines.append("")
    
    lines.append("---")
    lines.append("_Forrás: BettingExpert.com (verified tipsters)_")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test
    print("Testing BettingExpert scraper...\n")
    
    tips = scrape_football_tips(max_tips=30)
    
    if tips:
        print(f"\n{len(tips)} tips scraped\n")
        
        # Show first 3
        for i, tip in enumerate(tips[:3], 1):
            print(f"{i}. {tip['match']}")
            print(f"   Pick: {tip['pick']} @ {tip['odds']}")
            print(f"   Tipster: {tip['tipster']} ({tip['tipster_rating']})")
            print(f"   Confidence: {tip['confidence']}%")
            print()
        
        # Build consensus
        consensus = build_consensus_bettingexpert(tips, min_tips=2)
        
        if consensus:
            print(f"\n{len(consensus)} consensus picks\n")
            summary = format_bettingexpert_summary(consensus)
            print(summary)
        else:
            print("\nNo consensus (need 2+ tipsters per match)")
    else:
        print("\nNo tips found - site structure may have changed")
