#!/usr/bin/env python3
"""Football-Data.org FREE tier odds fetcher.

Regisztrálj: https://www.football-data.org/client/register
- 10 requests/minute
- Top 12 leagues
- 1X2 odds included (Bet365)
- TELJESEN INGYENES, nincs bankkártya
"""
import os
import requests
from typing import Dict, Optional, List
import time

API_KEY = os.getenv("FOOTBALLDATA_API_KEY", "").strip()
BASE_URL = "https://api.football-data.org/v4"

# Top leagues with FREE tier odds
COMPETITIONS = {
    "PL": 2021,   # Premier League
    "PD": 2014,   # La Liga
    "BL1": 2002,  # Bundesliga
    "SA": 2019,   # Serie A
    "FL1": 2015,  # Ligue 1
    "DED": 2003,  # Eredivisie
    "PPL": 2017,  # Primeira Liga
    "CL": 2001,   # Champions League
    "EL": 2018,   # Europa League
    "ELC": 2016,  # Championship
}

_cache = {}

def get_odds_for_match(home_team: str, away_team: str, date_str: str = None) -> Optional[Dict[str, float]]:
    """Get 1X2 odds from Football-Data.org.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        date_str: Match date (YYYY-MM-DD), default today
    
    Returns:
        {"1": 2.10, "X": 3.40, "2": 3.80} or None
    """
    if not API_KEY:
        print("[FootballData] FOOTBALLDATA_API_KEY not set!")
        return None
    
    home_norm = _normalize(home_team)
    away_norm = _normalize(away_team)
    
    # Try to find match in each competition
    for comp_code, comp_id in COMPETITIONS.items():
        if comp_id in _cache:
            matches = _cache[comp_id]
        else:
            matches = _fetch_matches(comp_id, date_str)
            _cache[comp_id] = matches
            time.sleep(6)  # Rate limit: 10 req/min
        
        for match in matches:
            if _normalize(match.get("homeTeam", "")) == home_norm and \
               _normalize(match.get("awayTeam", "")) == away_norm:
                odds = match.get("odds")
                if odds:
                    print(f"[FootballData] Match found in {comp_code}: {home_team} vs {away_team}")
                    return odds
    
    print(f"[FootballData] No match found for {home_team} vs {away_team}")
    return None

def _fetch_matches(comp_id: int, date_str: str = None) -> List[Dict]:
    """Fetch matches for a competition."""
    from datetime import date
    if not date_str:
        date_str = date.today().strftime("%Y-%m-%d")
    
    url = f"{BASE_URL}/competitions/{comp_id}/matches"
    headers = {"X-Auth-Token": API_KEY}
    params = {"dateFrom": date_str, "dateTo": date_str}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if r.status_code == 429:
            print(f"[FootballData] Rate limit hit for comp {comp_id}")
            return []
        
        if r.status_code == 403:
            print(f"[FootballData] Competition {comp_id} not in FREE tier")
            return []
        
        if r.status_code != 200:
            print(f"[FootballData] HTTP {r.status_code} for comp {comp_id}")
            return []
        
        data = r.json()
        matches = []
        
        for match in data.get("matches", []):
            home = (match.get("homeTeam") or {}).get("name", "")
            away = (match.get("awayTeam") or {}).get("name", "")
            
            # Extract Bet365 odds (most reliable bookmaker)
            odds_data = match.get("odds", {})
            
            if not odds_data:
                continue
            
            # Try different formats
            bet365 = None
            if "bet365" in str(odds_data).lower():
                bet365 = odds_data.get("bet365") or odds_data.get("Bet365")
            
            # Or direct keys
            if not bet365:
                home_win = odds_data.get("homeWin")
                draw = odds_data.get("draw")
                away_win = odds_data.get("awayWin")
                
                if home_win and draw and away_win:
                    bet365 = {
                        "homeWin": home_win,
                        "draw": draw,
                        "awayWin": away_win
                    }
            
            if bet365:
                try:
                    odds = {
                        "1": float(bet365.get("homeWin")),
                        "X": float(bet365.get("draw")),
                        "2": float(bet365.get("awayWin"))
                    }
                    
                    matches.append({
                        "homeTeam": home,
                        "awayTeam": away,
                        "odds": odds
                    })
                except:
                    pass
        
        print(f"[FootballData] Fetched {len(matches)} matches with odds from comp {comp_id}")
        return matches
    
    except Exception as e:
        print(f"[FootballData] Error fetching comp {comp_id}: {repr(e)}")
        return []

def _normalize(team: str) -> str:
    """Normalize team name for matching."""
    return "".join(c.lower() for c in team if c.isalnum())

if __name__ == "__main__":
    # Test
    odds = get_odds_for_match("RB Leipzig", "Hoffenheim", "2026-03-20")
    print(f"\nOdds: {odds}")
