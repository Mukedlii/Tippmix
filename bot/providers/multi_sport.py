"""
bot/providers/multi_sport.py

Multi-sport támogatás (kosárlabda, kézilabda, jégkorong).
Használat: pool bővítés ha foci kevés.
"""

from __future__ import annotations

import os
import time
import random
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        time.sleep(random.uniform(0.8, 1.5))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.debug(f"HTTP {r.status_code} → {url}")
    except Exception as e:
        log.debug(f"Fetch failed {url}: {e}")
    return None


# ──────────────────────────────────────────────
# 1. KOSÁRLABDA (NBA, Euroleague, NBL)
# ──────────────────────────────────────────────

def fetch_basketball_matches(date_str: str = None) -> List[Dict[str, Any]]:
    """
    Kosárlabda meccsek lekérése (FlashScore / SofaScore scraping).
    
    Returns:
        [{"sport": "basketball", "league_name": "NBA", "home_team": "Lakers", ...}]
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    matches = []
    
    # FlashScore kosárlabda
    url = f"https://www.flashscore.com/basketball/"
    html = _get(url)
    if not html:
        log.info("[Basketball] FlashScore scraping failed")
        return matches
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # FlashScore dinamikus, best-effort scraping
        events = soup.select("div.event__match, div.sportName")[:20]
        
        for event in events:
            home_el = event.select_one("div.event__participant--home")
            away_el = event.select_one("div.event__participant--away")
            time_el = event.select_one("div.event__time")
            league_el = event.select_one("span.event__title")
            
            if not (home_el and away_el):
                continue
            
            home_team = home_el.get_text(strip=True)
            away_team = away_el.get_text(strip=True)
            kickoff = time_el.get_text(strip=True) if time_el else ""
            league = league_el.get_text(strip=True) if league_el else "Basketball"
            
            # Csak ma/holnap meccsek
            if not kickoff or ":" not in kickoff:
                continue
            
            matches.append({
                "sport": "basketball",
                "fixture_id": hash(f"{home_team}{away_team}{kickoff}"),
                "league_name": league,
                "country_name": "International",
                "kickoff_local": f"{date_str}T{kickoff}:00+00:00",
                "home_team": home_team,
                "away_team": away_team,
                "odds": {},
                "standings": {},
                "injuries": [],
                "source": "flashscore",
            })
        
        log.info(f"[Basketball] FlashScore: {len(matches)} meccs")
    
    except Exception as e:
        log.debug(f"[Basketball] FlashScore parse error: {e}")
    
    return matches


# ──────────────────────────────────────────────
# 2. KÉZILABDA (EHF, válogatott)
# ──────────────────────────────────────────────

def fetch_handball_matches(date_str: str = None) -> List[Dict[str, Any]]:
    """
    Kézilabda meccsek lekérése (FlashScore scraping).
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    matches = []
    
    url = f"https://www.flashscore.com/handball/"
    html = _get(url)
    if not html:
        log.info("[Handball] FlashScore scraping failed")
        return matches
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        events = soup.select("div.event__match")[:15]
        
        for event in events:
            home_el = event.select_one("div.event__participant--home")
            away_el = event.select_one("div.event__participant--away")
            time_el = event.select_one("div.event__time")
            league_el = event.select_one("span.event__title")
            
            if not (home_el and away_el):
                continue
            
            home_team = home_el.get_text(strip=True)
            away_team = away_el.get_text(strip=True)
            kickoff = time_el.get_text(strip=True) if time_el else ""
            league = league_el.get_text(strip=True) if league_el else "Handball"
            
            if not kickoff or ":" not in kickoff:
                continue
            
            matches.append({
                "sport": "handball",
                "fixture_id": hash(f"{home_team}{away_team}{kickoff}"),
                "league_name": league,
                "country_name": "International",
                "kickoff_local": f"{date_str}T{kickoff}:00+00:00",
                "home_team": home_team,
                "away_team": away_team,
                "odds": {},
                "standings": {},
                "injuries": [],
                "source": "flashscore",
            })
        
        log.info(f"[Handball] FlashScore: {len(matches)} meccs")
    
    except Exception as e:
        log.debug(f"[Handball] FlashScore parse error: {e}")
    
    return matches


# ──────────────────────────────────────────────
# 3. JÉGKORONG (NHL, opcionális)
# ──────────────────────────────────────────────

def fetch_hockey_matches(date_str: str = None) -> List[Dict[str, Any]]:
    """
    Jégkorong meccsek (opcionális).
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    matches = []
    
    url = f"https://www.flashscore.com/hockey/"
    html = _get(url)
    if not html:
        return matches
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        events = soup.select("div.event__match")[:10]
        
        for event in events:
            home_el = event.select_one("div.event__participant--home")
            away_el = event.select_one("div.event__participant--away")
            time_el = event.select_one("div.event__time")
            league_el = event.select_one("span.event__title")
            
            if not (home_el and away_el):
                continue
            
            home_team = home_el.get_text(strip=True)
            away_team = away_el.get_text(strip=True)
            kickoff = time_el.get_text(strip=True) if time_el else ""
            league = league_el.get_text(strip=True) if league_el else "Hockey"
            
            if not kickoff or ":" not in kickoff:
                continue
            
            matches.append({
                "sport": "hockey",
                "fixture_id": hash(f"{home_team}{away_team}{kickoff}"),
                "league_name": league,
                "country_name": "International",
                "kickoff_local": f"{date_str}T{kickoff}:00+00:00",
                "home_team": home_team,
                "away_team": away_team,
                "odds": {},
                "standings": {},
                "injuries": [],
                "source": "flashscore",
            })
        
        log.info(f"[Hockey] FlashScore: {len(matches)} meccs")
    
    except Exception as e:
        log.debug(f"[Hockey] FlashScore parse error: {e}")
    
    return matches


# ──────────────────────────────────────────────
# 4. FŐ FÜGGVÉNY - Multi-sport pool bővítés
# ──────────────────────────────────────────────

def fetch_multi_sport_matches(
    date_str: str = None,
    min_pool_size: int = 15,
    current_pool: List[Dict[str, Any]] = None,
    sports: List[str] = None,
) -> List[Dict[str, Any]]:
    """
    Multi-sport pool bővítés.
    
    Args:
        date_str: YYYY-MM-DD
        min_pool_size: Minimum meccsek száma
        current_pool: Jelenlegi foci pool
        sports: Engedélyezett sportok (["basketball", "handball", "hockey"])
    
    Returns:
        Kiegészített pool (foci + egyéb sportok)
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    if current_pool is None:
        current_pool = []
    
    if sports is None:
        # Default: kosár + kézi
        sports = os.getenv("TIPPMIX_EXTRA_SPORTS", "basketball,handball").split(",")
        sports = [s.strip().lower() for s in sports if s.strip()]
    
    # Ha elég foci van, return
    if len(current_pool) >= min_pool_size:
        log.info(f"[MultiSport] Foci pool elég nagy ({len(current_pool)}), nem kell bővítés")
        return current_pool
    
    log.info(f"[MultiSport] Foci pool kicsi ({len(current_pool)}), bővítés: {sports}")
    
    all_matches = list(current_pool)
    
    # Kosárlabda
    if "basketball" in sports and len(all_matches) < min_pool_size:
        basketball = fetch_basketball_matches(date_str)
        all_matches.extend(basketball)
        log.info(f"[MultiSport] Kosár hozzáadva: {len(basketball)} meccs")
    
    # Kézilabda
    if "handball" in sports and len(all_matches) < min_pool_size:
        handball = fetch_handball_matches(date_str)
        all_matches.extend(handball)
        log.info(f"[MultiSport] Kézi hozzáadva: {len(handball)} meccs")
    
    # Jégkorong (opcionális)
    if "hockey" in sports and len(all_matches) < min_pool_size:
        hockey = fetch_hockey_matches(date_str)
        all_matches.extend(hockey)
        log.info(f"[MultiSport] Jégkorong hozzáadva: {len(hockey)} meccs")
    
    log.info(f"[MultiSport] Végső pool: {len(all_matches)} meccs (foci: {len(current_pool)}, egyéb: {len(all_matches) - len(current_pool)})")
    
    return all_matches


# ──────────────────────────────────────────────
# 5. Sport emoji + formázás
# ──────────────────────────────────────────────

def get_sport_emoji(sport: str) -> str:
    """Sport emoji a Telegram üzenetekhez."""
    sport = (sport or "football").lower()
    
    if sport == "basketball":
        return "🏀"
    elif sport == "handball":
        return "🤾"
    elif sport == "hockey":
        return "🏒"
    elif sport == "volleyball":
        return "🏐"
    elif sport == "tennis":
        return "🎾"
    else:
        return "⚽"  # football default


def format_match_with_sport(match: Dict[str, Any]) -> str:
    """
    Meccs formázás sport ikonnal.
    
    Returns:
        "🏀 Lakers vs Celtics"
    """
    sport = match.get("sport", "football")
    emoji = get_sport_emoji(sport)
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    
    return f"{emoji} {home} vs {away}"
