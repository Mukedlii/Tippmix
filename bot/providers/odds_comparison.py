#!/usr/bin/env python3
"""
Odds Comparison Tool

Compares odds across multiple bookmakers and finds the best value.
Sources:
- Oddsportal.com (free, public odds)
- TheOddsAPI (if available)
- SofaScore (if available)
"""

import re
import time
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


def search_match_on_oddsportal(home_team: str, away_team: str) -> Optional[str]:
    """
    Search for match on Oddsportal
    
    Returns:
        Match URL or None
    """
    
    # Simplified team names (remove common suffixes)
    home_clean = home_team.replace('FC', '').replace('CF', '').replace('United', '').strip()
    away_clean = away_team.replace('FC', '').replace('CF', '').replace('United', '').strip()
    
    query = f"{home_clean} {away_clean}".replace(' ', '-').lower()
    search_url = f"https://www.oddsportal.com/search/{query}/"
    
    try:
        time.sleep(2)  # Be polite
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find match link
        for link in soup.select('a[href*="/football/"]'):
            href = link.get('href', '')
            text = link.text.lower()
            
            if home_clean.lower() in text and away_clean.lower() in text:
                return "https://www.oddsportal.com" + href
        
        return None
        
    except Exception as e:
        print(f"Oddsportal search error: {e}")
        return None


def get_odds_from_oddsportal(match_url: str) -> Dict[str, Dict[str, float]]:
    """
    Scrape odds from Oddsportal match page
    
    Returns:
        {
            "bet365": {"1": 2.10, "X": 3.40, "2": 3.60},
            "unibet": {"1": 2.05, "X": 3.50, "2": 3.55},
            ...
        }
    """
    
    try:
        time.sleep(2)
        resp = requests.get(match_url, headers=HEADERS, timeout=15)
        
        if resp.status_code != 200:
            return {}
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        bookmaker_odds = {}
        
        # Oddsportal structure varies - simplified parsing
        # Look for odds in table rows
        for row in soup.select('tr'):
            # Find bookmaker name
            bookie_cell = row.select_one('a.name')
            if not bookie_cell:
                continue
            
            bookie_name = bookie_cell.text.strip().lower()
            
            # Find odds cells
            odds_cells = row.select('td.odds')
            if len(odds_cells) >= 3:
                try:
                    odds_1 = float(odds_cells[0].text.strip())
                    odds_x = float(odds_cells[1].text.strip())
                    odds_2 = float(odds_cells[2].text.strip())
                    
                    bookmaker_odds[bookie_name] = {
                        "1": odds_1,
                        "X": odds_x,
                        "2": odds_2
                    }
                except (ValueError, IndexError):
                    continue
        
        return bookmaker_odds
        
    except Exception as e:
        print(f"Oddsportal parse error: {e}")
        return {}


def find_best_odds(home_team: str, away_team: str, pick: str) -> Dict:
    """
    Find best odds for a pick across bookmakers
    
    Args:
        home_team: Home team name
        away_team: Away team name
        pick: "Hazai győzelem" | "Döntetlen" | "Vendég győzelem"
    
    Returns:
        {
            "best_bookie": str,
            "best_odds": float,
            "all_bookies": {bookie: odds},
            "profit_diff": float  # vs worst bookie (%)
        }
    """
    
    # Map Hungarian pick to 1X2
    pick_map = {
        "hazai győzelem": "1",
        "hazai gyozelem": "1",
        "döntetlen": "X",
        "dontetlen": "X",
        "vendég győzelem": "2",
        "vendeg gyozelem": "2"
    }
    
    pick_code = pick_map.get(pick.lower())
    if not pick_code:
        return {}
    
    # Search match
    match_url = search_match_on_oddsportal(home_team, away_team)
    if not match_url:
        return {}
    
    # Get odds
    bookmaker_odds = get_odds_from_oddsportal(match_url)
    if not bookmaker_odds:
        return {}
    
    # Extract odds for the pick
    pick_odds = {}
    for bookie, odds_dict in bookmaker_odds.items():
        if pick_code in odds_dict:
            pick_odds[bookie] = odds_dict[pick_code]
    
    if not pick_odds:
        return {}
    
    # Find best
    best_bookie = max(pick_odds, key=pick_odds.get)
    best_odds = pick_odds[best_bookie]
    worst_odds = min(pick_odds.values())
    
    profit_diff = ((best_odds - worst_odds) / worst_odds) * 100
    
    return {
        "best_bookie": best_bookie,
        "best_odds": round(best_odds, 2),
        "all_bookies": {k: round(v, 2) for k, v in pick_odds.items()},
        "profit_diff": round(profit_diff, 1)
    }


def format_odds_comparison(comparison: Dict, stake: int = 1000) -> str:
    """
    Format odds comparison for display
    
    Args:
        comparison: Result from find_best_odds()
        stake: Bet amount in HUF
    
    Returns:
        Formatted string
    """
    
    if not comparison:
        return "Odds comparison not available"
    
    best = comparison['best_bookie']
    best_odds = comparison['best_odds']
    all_bookies = comparison['all_bookies']
    profit_diff = comparison['profit_diff']
    
    lines = [f"BEST ODDS: {best.upper()} @ {best_odds}"]
    
    # Show all bookies
    sorted_bookies = sorted(all_bookies.items(), key=lambda x: x[1], reverse=True)
    
    for bookie, odds in sorted_bookies[:5]:  # Top 5
        marker = " <- BEST" if bookie == best else ""
        lines.append(f"  {bookie}: {odds}{marker}")
    
    # Profit comparison
    if profit_diff > 0:
        extra_profit = int(stake * (profit_diff / 100))
        lines.append(f"\nExtra profit vs worst: +{extra_profit} HUF on {stake} HUF stake")
    
    return "\n".join(lines)


def enrich_picks_with_best_odds(picks: List[Dict]) -> List[Dict]:
    """
    Add best_odds info to each pick
    
    Modifies picks in-place, adds:
    - best_bookie
    - best_odds
    - odds_comparison_text
    """
    
    for pick in picks:
        home = pick.get('home_team')
        away = pick.get('away_team')
        tip = pick.get('tip')
        
        if not (home and away and tip):
            continue
        
        print(f"Fetching odds for {home} vs {away}...")
        
        comparison = find_best_odds(home, away, tip)
        
        if comparison:
            pick['best_bookie'] = comparison['best_bookie']
            pick['best_odds'] = comparison['best_odds']
            pick['odds_comparison'] = comparison
            pick['odds_comparison_text'] = format_odds_comparison(comparison)
        
        time.sleep(3)  # Rate limiting
    
    return picks


if __name__ == "__main__":
    # Test
    print("Testing odds comparison...\n")
    
    result = find_best_odds(
        "Manchester United",
        "Liverpool",
        "Vendég győzelem"
    )
    
    if result:
        print(format_odds_comparison(result, stake=1000))
    else:
        print("No odds found")
