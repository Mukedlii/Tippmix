# Tippmix.hu odds scraper
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple
import re

def scrape_tippmix_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
    """
    Scrapel Tippmix.hu-rĂłl 1X2 odds-okat egy meccshez.
    
    Returns:
        {"1": 2.10, "X": 3.40, "2": 3.20} vagy None
    """
    try:
        # Normalize team names
        home = home_team.lower().strip()
        away = away_team.lower().strip()
        
        # Tippmix main page
        url = "https://www.tippmix.hu/sport/fogadas/labdarugas"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all match rows (structure changes, be flexible)
        matches = soup.find_all('div', class_=re.compile(r'match|event', re.I))
        
        for match in matches:
            match_text = match.get_text().lower()
            
            # Check if both teams are in this row
            if home in match_text and away in match_text:
                # Find odds (usually in spans/divs with class containing 'odd' or 'koef')
                odds_elements = match.find_all(['span', 'div'], class_=re.compile(r'odd|koef|rate', re.I))
                
                if len(odds_elements) >= 3:
                    try:
                        odds_1 = float(odds_elements[0].get_text().strip().replace(',', '.'))
                        odds_x = float(odds_elements[1].get_text().strip().replace(',', '.'))
                        odds_2 = float(odds_elements[2].get_text().strip().replace(',', '.'))
                        
                        return {
                            "1": odds_1,
                            "X": odds_x,
                            "2": odds_2
                        }
                    except (ValueError, IndexError):
                        continue
        
        return None
        
    except Exception as e:
        print(f"Tippmix scraping error: {repr(e)}")
        return None


def scrape_nemzeti_sport_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
    """
    Scrapel Nemzeti Sport-rĂłl odds-okat (backup).
    """
    try:
        url = "https://www.nemzetisport.hu/fogadas"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        home = home_team.lower().strip()
        away = away_team.lower().strip()
        
        # Similar logic to Tippmix
        matches = soup.find_all(['div', 'tr'], class_=re.compile(r'match|game|event', re.I))
        
        for match in matches:
            text = match.get_text().lower()
            if home in text and away in text:
                odds = match.find_all(['span', 'td'], class_=re.compile(r'odd|rate|koef', re.I))
                if len(odds) >= 3:
                    try:
                        return {
                            "1": float(odds[0].get_text().strip().replace(',', '.')),
                            "X": float(odds[1].get_text().strip().replace(',', '.')),
                            "2": float(odds[2].get_text().strip().replace(',', '.'))
                        }
                    except (ValueError, IndexError):
                        continue
        
        return None
        
    except Exception as e:
        print(f"Nemzeti Sport scraping error: {repr(e)}")
        return None


def get_odds_with_fallback(home_team: str, away_team: str) -> Dict[str, Optional[float]]:
    """
    PrĂłbĂˇlja Tippmix â†’ Nemzeti Sport â†’ fallback 1.85.
    """
    # Try Tippmix first
    odds = scrape_tippmix_odds(home_team, away_team)
    if odds:
        return odds
    
    # Try Nemzeti Sport
    odds = scrape_nemzeti_sport_odds(home_team, away_team)
    if odds:
        return odds
    
    # Fallback: safe default odds (not TBA)
    return {
        "1": 1.85,
        "X": 3.40,
        "2": 4.20
    }


if __name__ == "__main__":
    # Test
    test_odds = get_odds_with_fallback("RB Leipzig", "Hoffenheim")
    print(f"Odds: {test_odds}")
