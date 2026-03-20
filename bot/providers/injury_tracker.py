#!/usr/bin/env python3
"""
Injury Tracker - Transfermarkt scraping

Tracks player injuries and returns for major teams.
Integrates with Poisson model to adjust predictions.

Free source: Transfermarkt.com (public data)
"""

import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def get_team_injuries(team_name: str) -> Optional[Dict]:
    """
    Get injury list for a team from Transfermarkt
    
    Args:
        team_name: Team name (e.g., "Manchester United")
    
    Returns:
        {
            "team": str,
            "injuries": [
                {
                    "player": str,
                    "position": str,
                    "injury": str,
                    "until": str,  # Date or "?"
                    "severity": str  # "major" | "minor" | "unknown"
                }
            ],
            "source": "transfermarkt",
            "fetched_at": str
        }
    """
    
    # Transfermarkt team search
    search_url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={team_name.replace(' ', '+')}"
    
    try:
        time.sleep(1.5)  # Be polite
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find team link
        team_link = None
        for link in soup.select('a[href*="/verein/"]'):
            if team_name.lower() in link.text.lower():
                team_link = "https://www.transfermarkt.com" + link['href']
                break
        
        if not team_link:
            return None
        
        # Get injuries page
        injury_url = team_link.replace('/startseite/', '/verletztenlazarett/') + "/saison_id/2025"
        
        time.sleep(1.5)
        injury_resp = requests.get(injury_url, headers=HEADERS, timeout=15)
        
        if injury_resp.status_code != 200:
            return None
        
        injury_soup = BeautifulSoup(injury_resp.text, 'html.parser')
        
        injuries = []
        
        # Parse injury table
        for row in injury_soup.select('table.items tbody tr'):
            try:
                player_cell = row.select_one('td.hauptlink a')
                if not player_cell:
                    continue
                
                player_name = player_cell.text.strip()
                
                position_cell = row.select('td')[1] if len(row.select('td')) > 1 else None
                position = position_cell.text.strip() if position_cell else "Unknown"
                
                injury_cell = row.select('td')[3] if len(row.select('td')) > 3 else None
                injury_type = injury_cell.text.strip() if injury_cell else "Unknown"
                
                until_cell = row.select('td')[4] if len(row.select('td')) > 4 else None
                until_date = until_cell.text.strip() if until_cell else "?"
                
                # Assess severity
                severity = "unknown"
                if injury_type and injury_cell:
                    injury_lower = injury_type.lower()
                    if any(x in injury_lower for x in ["acl", "cruciate", "fracture", "broken", "surgery"]):
                        severity = "major"
                    elif any(x in injury_lower for x in ["knock", "bruise", "minor"]):
                        severity = "minor"
                    else:
                        severity = "moderate"
                
                injuries.append({
                    "player": player_name,
                    "position": position,
                    "injury": injury_type,
                    "until": until_date,
                    "severity": severity
                })
                
            except Exception:
                continue
        
        return {
            "team": team_name,
            "injuries": injuries,
            "source": "transfermarkt",
            "fetched_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        print(f"Error fetching injuries for {team_name}: {e}")
        return None


def assess_injury_impact(injuries: List[Dict]) -> Dict[str, float]:
    """
    Assess overall injury impact on team
    
    Returns:
        {
            "attack_penalty": float,  # 0.0 - 1.0 (higher = worse)
            "defense_penalty": float,
            "overall_severity": str  # "none" | "minor" | "moderate" | "severe"
        }
    """
    
    if not injuries:
        return {
            "attack_penalty": 0.0,
            "defense_penalty": 0.0,
            "overall_severity": "none"
        }
    
    attack_positions = {"forward", "striker", "winger", "attacking", "centre-forward"}
    defense_positions = {"defender", "centre-back", "full-back", "goalkeeper"}
    
    attack_impact = 0.0
    defense_impact = 0.0
    
    for inj in injuries:
        pos = inj.get("position", "").lower()
        severity = inj.get("severity", "unknown")
        
        # Weight by severity
        weight = 0.3  # default
        if severity == "major":
            weight = 1.0
        elif severity == "moderate":
            weight = 0.6
        elif severity == "minor":
            weight = 0.2
        
        # Check position
        if any(p in pos for p in attack_positions):
            attack_impact += weight
        elif any(p in pos for p in defense_positions):
            defense_impact += weight
        else:
            # Midfielder or unknown - split impact
            attack_impact += weight * 0.4
            defense_impact += weight * 0.4
    
    # Normalize (cap at 1.0)
    attack_penalty = min(attack_impact / 3.0, 1.0)  # 3 major injuries = max
    defense_penalty = min(defense_impact / 3.0, 1.0)
    
    # Overall severity
    total = attack_penalty + defense_penalty
    if total < 0.2:
        overall = "minor"
    elif total < 0.6:
        overall = "moderate"
    else:
        overall = "severe"
    
    return {
        "attack_penalty": attack_penalty,
        "defense_penalty": defense_penalty,
        "overall_severity": overall if injuries else "none"
    }


def format_injury_summary(team_injuries: Dict) -> str:
    """Format injury data for Telegram/logging"""
    
    if not team_injuries or not team_injuries.get("injuries"):
        return f"{team_injuries.get('team', 'Team')}: No injuries"
    
    team = team_injuries['team']
    injuries = team_injuries['injuries']
    impact = assess_injury_impact(injuries)
    
    lines = [f"{team} INJURIES ({len(injuries)}):"]
    lines.append(f"Impact: {impact['overall_severity'].upper()}")
    lines.append("")
    
    for inj in injuries[:10]:  # Max 10
        player = inj['player']
        injury = inj['injury']
        until = inj['until']
        severity_icon = {"major": "RED", "moderate": "ORANGE", "minor": "YELLOW", "unknown": "?"}.get(inj['severity'], "?")
        
        lines.append(f"  [{severity_icon}] {player} - {injury} (until {until})")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test
    print("Testing injury tracker...\n")
    
    test_teams = ["Manchester United", "Liverpool", "Arsenal"]
    
    for team in test_teams:
        print(f"\nFetching {team}...")
        data = get_team_injuries(team)
        
        if data:
            print(format_injury_summary(data))
        else:
            print(f"  Failed to fetch data for {team}")
        
        time.sleep(2)  # Rate limiting
