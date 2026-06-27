"""
bot/scrapers/result_scraper.py

Fetch completed match results from multiple sources:
- TheOddsAPI (primary)
- FlashScore (secondary)
- SportMonks (if available)

Auto-update database with final scores.
"""

import os
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
import sqlite3

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# 1. TheOddsAPI Results
# ─────────────────────────────────────────────────────────────────

def fetch_results_theoddsapi(
    days_back: int = 3,
    max_requests: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch completed match results from TheOddsAPI.
    
    Args:
        days_back: How many days to look back
        max_requests: Rate limit budget
    
    Returns:
        List of completed matches with scores
    """
    
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        log.warning("[TheOddsAPI] No API key set")
        return []
    
    results = []
    sports = [
        "soccer_epl",           # Premier League
        "soccer_spain_la_liga", # La Liga
        "soccer_germany_bundesliga",  # Bundesliga
        "soccer_italy_serie_a", # Serie A
        "soccer_france_ligue_one",  # Ligue 1
        "soccer_uefa_champs_league",  # Champions League
    ]
    
    request_count = 0
    
    for sport in sports:
        if request_count >= max_requests:
            log.info(f"[TheOddsAPI] Rate limit reached ({request_count}/{max_requests})")
            break
        
        try:
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores/"
            params = {
                "apiKey": api_key,
                "daysFrom": days_back,
                "dateFormat": "iso",
            }
            
            log.info(f"[TheOddsAPI] Fetching {sport}...")
            response = requests.get(url, params=params, timeout=15)
            request_count += 1
            
            if response.status_code != 200:
                log.warning(f"[TheOddsAPI] HTTP {response.status_code} for {sport}")
                continue
            
            data = response.json()
            
            for match in data:
                if not match.get("completed"):
                    continue
                
                # Parse scores
                scores = match.get("scores", [])
                home_score = None
                away_score = None
                
                for score in scores:
                    if score.get("name") == match.get("home_team"):
                        home_score = score.get("score")
                    elif score.get("name") == match.get("away_team"):
                        away_score = score.get("score")
                
                if home_score is None or away_score is None:
                    continue
                
                results.append({
                    "source": "theoddsapi",
                    "sport": sport,
                    "home_team": match.get("home_team"),
                    "away_team": match.get("away_team"),
                    "home_score": int(home_score),
                    "away_score": int(away_score),
                    "kickoff": match.get("commence_time"),
                    "completed_at": match.get("last_update"),
                })
            
            completed_count = len([m for m in data if m.get("completed")])
            log.info(f"[TheOddsAPI] {sport}: {completed_count} completed matches")
        
        except Exception as e:
            log.error(f"[TheOddsAPI] Error fetching {sport}: {repr(e)}")
            continue
    
    log.info(f"[TheOddsAPI] Total: {len(results)} results")
    return results


# ─────────────────────────────────────────────────────────────────
# 2. FlashScore Scraper
# ─────────────────────────────────────────────────────────────────

def fetch_results_flashscore(
    days_back: int = 1
) -> List[Dict[str, Any]]:
    """
    Scrape completed match results from FlashScore.
    
    Args:
        days_back: How many days to look back
    
    Returns:
        List of completed matches with scores
    """
    
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("[FlashScore] BeautifulSoup not installed")
        return []
    
    results = []
    
    try:
        # FlashScore today's results
        url = "https://www.flashscore.com/football/"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        
        log.info(f"[FlashScore] Fetching {url}...")
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code != 200:
            log.warning(f"[FlashScore] HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find completed matches
        match_rows = soup.find_all("div", class_=lambda x: x and "event__match" in x)
        
        for row in match_rows[:50]:  # Limit to 50 matches
            try:
                # Extract teams
                teams = row.find_all("span", class_=lambda x: x and "event__participant" in x)
                if len(teams) < 2:
                    continue
                
                home_team = teams[0].get_text(strip=True)
                away_team = teams[1].get_text(strip=True)
                
                # Extract score
                score_elem = row.find("span", class_=lambda x: x and "event__score" in x)
                if not score_elem:
                    continue
                
                score_text = score_elem.get_text(strip=True)
                
                # Parse score (e.g., "2:1")
                if ":" not in score_text:
                    continue
                
                try:
                    home_score, away_score = map(int, score_text.split(":"))
                except ValueError:
                    continue
                
                results.append({
                    "source": "flashscore",
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_score,
                    "away_score": away_score,
                    "kickoff": None,  # FlashScore doesn't provide time easily
                })
            
            except Exception as e:
                log.debug(f"[FlashScore] Error parsing match: {repr(e)}")
                continue
        
        log.info(f"[FlashScore] Total: {len(results)} results")
        return results
    
    except Exception as e:
        log.error(f"[FlashScore] Error: {repr(e)}")
        return []


# ─────────────────────────────────────────────────────────────────
# 3. SportMonks Results (if API key available)
# ─────────────────────────────────────────────────────────────────

def fetch_results_sportmonks(
    days_back: int = 1
) -> List[Dict[str, Any]]:
    """
    Fetch results from SportMonks API.
    
    Args:
        days_back: How many days to look back
    
    Returns:
        List of completed matches
    """
    
    api_key = os.getenv("SPORTMONKS_API_TOKEN")
    if not api_key:
        log.debug("[SportMonks] No API key set")
        return []
    
    results = []
    
    try:
        # Calculate date range
        start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()
        end_date = datetime.now(timezone.utc).date()
        
        url = "https://api.sportmonks.com/v3/football/fixtures"
        
        params = {
            "api_token": api_key,
            "filters": f"dateFrom:{start_date},dateTo:{end_date}",
            "include": "teams,scores",
            "per_page": 100,
        }
        
        log.info(f"[SportMonks] Fetching {start_date} to {end_date}...")
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            log.warning(f"[SportMonks] HTTP {response.status_code}")
            return []
        
        data = response.json()
        
        for fixture in data.get("data", []):
            # Check if match is finished
            if fixture.get("status") != "finished":
                continue
            
            home_team = fixture.get("teams", {}).get("home", {}).get("name")
            away_team = fixture.get("teams", {}).get("away", {}).get("name")
            
            # Get scores
            scores = fixture.get("scores", {})
            home_score = scores.get("home")
            away_score = scores.get("away")
            
            if not all([home_team, away_team, home_score is not None, away_score is not None]):
                continue
            
            results.append({
                "source": "sportmonks",
                "home_team": home_team,
                "away_team": away_team,
                "home_score": int(home_score),
                "away_score": int(away_score),
                "kickoff": fixture.get("date"),
            })
        
        log.info(f"[SportMonks] Total: {len(results)} results")
        return results
    
    except Exception as e:
        log.error(f"[SportMonks] Error: {repr(e)}")
        return []


# ─────────────────────────────────────────────────────────────────
# 4. Database Update
# ─────────────────────────────────────────────────────────────────

def save_results_to_db(
    results: List[Dict[str, Any]],
    db_path: Optional[str] = None
) -> int:
    """
    Save match results to database.
    
    Args:
        results: List of match results
        db_path: Database path
    
    Returns:
        Number of results saved/updated
    """
    
    if not results:
        return 0
    
    db_path = db_path or os.getenv("TIPPMIX_DB_PATH", "data/tippmix.db")
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Create results table if not exists
        c.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_goals INTEGER,
                away_goals INTEGER,
                kickoff_ts_utc TEXT,
                source TEXT DEFAULT 'unknown',
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(home_team, away_team, kickoff_ts_utc)
            )
        """)
        
        saved_count = 0
        
        for result in results:
            try:
                c.execute("""
                    INSERT OR REPLACE INTO results
                    (home_team, away_team, home_goals, away_goals, kickoff_ts_utc, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    result["home_team"],
                    result["away_team"],
                    result["home_score"],
                    result["away_score"],
                    result.get("kickoff"),
                    result.get("source", "unknown"),
                ))
                saved_count += 1
            
            except sqlite3.IntegrityError:
                # Duplicate, update instead
                c.execute("""
                    UPDATE results
                    SET home_goals=?, away_goals=?, source=?, fetched_at=CURRENT_TIMESTAMP
                    WHERE home_team=? AND away_team=? AND kickoff_ts_utc=?
                """, (
                    result["home_score"],
                    result["away_score"],
                    result.get("source", "unknown"),
                    result["home_team"],
                    result["away_team"],
                    result.get("kickoff"),
                ))
                saved_count += 1
        
        conn.commit()
        conn.close()
        
        log.info(f"[DB] Saved {saved_count} results")
        return saved_count
    
    except Exception as e:
        log.error(f"[DB] Save failed: {repr(e)}")
        return 0


# ─────────────────────────────────────────────────────────────────
# 5. Main orchestrator
# ─────────────────────────────────────────────────────────────────

async def fetch_and_store_results(
    days_back: int = 1,
    db_path: Optional[str] = None
) -> Dict[str, int]:
    """
    Fetch results from all sources and save to DB.
    
    Args:
        days_back: How many days to look back
        db_path: Database path
    
    Returns:
        {source: count} stats
    """
    
    all_results = []
    stats = {}
    
    # TheOddsAPI (primary, most reliable)
    theo_results = fetch_results_theoddsapi(days_back=days_back, max_requests=10)
    all_results.extend(theo_results)
    stats["theoddsapi"] = len(theo_results)
    
    # FlashScore (backup)
    flash_results = fetch_results_flashscore(days_back=days_back)
    all_results.extend(flash_results)
    stats["flashscore"] = len(flash_results)
    
    # SportMonks (if available)
    sm_results = fetch_results_sportmonks(days_back=days_back)
    all_results.extend(sm_results)
    stats["sportmonks"] = len(sm_results)
    
    # Deduplicate by (home, away, score)
    unique_results = {}
    for result in all_results:
        key = (result["home_team"], result["away_team"], result["home_score"], result["away_score"])
        if key not in unique_results:
            unique_results[key] = result
    
    # Save to DB
    saved = save_results_to_db(list(unique_results.values()), db_path=db_path)
    stats["saved"] = saved
    
    log.info(f"[RESULTS] Stats: {stats}")
    return stats


# Usage:
#
# import asyncio
# from bot.scrapers.result_scraper import fetch_and_store_results
#
# stats = asyncio.run(fetch_and_store_results(days_back=1))
# print(stats)
# # {'theoddsapi': 15, 'flashscore': 8, 'sportmonks': 0, 'saved': 18}
