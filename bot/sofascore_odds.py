#!/usr/bin/env python3
"""SofaScore unofficial API for odds scraping."""
import requests
from typing import Dict, Optional, List, Any
import datetime

BASE_URL = "https://api.sofascore.com/api/v1"

def _headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

def get_events_by_date(date_str: str = None) -> List[Dict[str, Any]]:
    """Get football events for a specific date.
    
    Args:
        date_str: YYYY-MM-DD format (default: today)
    
    Returns:
        List of events with basic info
    """
    if not date_str:
        date_str = datetime.date.today().strftime("%Y-%m-%d")
    
    url = f"{BASE_URL}/sport/football/scheduled-events/{date_str}"
    
    try:
        r = requests.get(url, headers=_headers(), timeout=15)
        if r.status_code != 200:
            print(f"[SofaScore] HTTP {r.status_code}")
            return []
        
        data = r.json()
        events = data.get("events", [])
        print(f"[SofaScore] Found {len(events)} events for {date_str}")
        return events
    
    except Exception as e:
        print(f"[SofaScore] Error: {repr(e)}")
        return []

def get_odds_for_event(event_id: int) -> Optional[Dict[str, float]]:
    """Get 1X2 odds for a specific event.
    
    Args:
        event_id: SofaScore event ID
    
    Returns:
        {"1": 2.10, "X": 3.40, "2": 3.80} or None
    """
    url = f"{BASE_URL}/event/{event_id}/odds/1/all"
    
    try:
        r = requests.get(url, headers=_headers(), timeout=15)
        if r.status_code != 200:
            return None
        
        data = r.json()
        markets = data.get("markets", [])
        
        # Find "Full Time Result" / "1X2" market
        for market in markets:
            market_name = market.get("marketName", "").lower()
            if "full time result" in market_name or "1x2" in market_name or "match result" in market_name:
                choices = market.get("choices", [])
                
                odds = {}
                for choice in choices:
                    name = choice.get("name", "").strip()
                    fractional = choice.get("fractionalValue")
                    
                    # Convert fractional to decimal
                    if fractional and "/" in fractional:
                        try:
                            num, denom = fractional.split("/")
                            decimal = round(float(num) / float(denom) + 1, 2)
                        except:
                            continue
                    else:
                        decimal = choice.get("sourceOdds")
                        if not decimal:
                            continue
                        decimal = round(float(decimal), 2)
                    
                    # Map to 1X2
                    if "home" in name.lower() or name == "1":
                        odds["1"] = decimal
                    elif "draw" in name.lower() or name == "X":
                        odds["X"] = decimal
                    elif "away" in name.lower() or name == "2":
                        odds["2"] = decimal
                
                if odds.get("1") and odds.get("X") and odds.get("2"):
                    return odds
        
        return None
    
    except Exception as e:
        print(f"[SofaScore] Odds error for event {event_id}: {repr(e)}")
        return None

def find_match_odds(home_team: str, away_team: str, date_str: str = None) -> Optional[Dict[str, float]]:
    """Find odds for a specific match by team names.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        date_str: Match date (YYYY-MM-DD)
    
    Returns:
        {"1": x, "X": y, "2": z} or None
    """
    events = get_events_by_date(date_str)
    
    home_norm = home_team.lower().strip()
    away_norm = away_team.lower().strip()
    
    for event in events:
        home_obj = event.get("homeTeam", {})
        away_obj = event.get("awayTeam", {})
        
        home_name = home_obj.get("name", "").lower().strip()
        away_name = away_obj.get("name", "").lower().strip()
        
        # Fuzzy match
        if (home_norm in home_name or home_name in home_norm) and \
           (away_norm in away_name or away_name in away_norm):
            event_id = event.get("id")
            if event_id:
                print(f"[SofaScore] Match found: {home_obj.get('name')} vs {away_obj.get('name')} (ID: {event_id})")
                return get_odds_for_event(event_id)
    
    print(f"[SofaScore] No match found for {home_team} vs {away_team}")
    return None

if __name__ == "__main__":
    # Test
    odds = find_match_odds("RB Leipzig", "Hoffenheim", "2026-03-20")
    print(f"\nOdds: {odds}")
