import os
import time
from typing import Any, Dict, Optional
import requests

BASE_URL = "https://api.football-data.org/v4"


def _token() -> str:
    t = (os.getenv("FOOTBALL_DATA_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("FOOTBALL_DATA_TOKEN nincs beállítva (GitHub Secrets).")
    return t


def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Dict[str, Any]:
    headers = {"X-Auth-Token": _token()}
    url = f"{BASE_URL}{path}"

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"football-data HTTP {r.status_code}: {r.text[:600]}")
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"football-data request failed: {repr(last_err)}")


# Egyszerű mapping – bővíthető
LEAGUE_NAME_TO_CODE = {
    "premier league": "PL",
    "la liga": "PD",
    "primera division": "PD",
    "serie a": "SA",
    "bundesliga": "BL1",
    "ligue 1": "FL1",
    "eredivisie": "DED",
    "primeira liga": "PPL",
    "scottish premiership": "SPL",
    "championship": "ELC",
}


def guess_competition_code(league_name: str) -> Optional[str]:
    key = (league_name or "").strip().lower()
    for k, v in LEAGUE_NAME_TO_CODE.items():
        if k in key:
            return v
    return None


def get_standings_for_comp(code: str) -> Dict[str, Any]:
    return _get(f"/competitions/{code}/standings")


def get_matches_for_comp(code: str, season: Optional[int] = None, status: str = "FINISHED") -> Dict[str, Any]:
    """
    Fetch matches for a competition.
    
    Args:
        code: Competition code (e.g., "PL", "CL")
        season: Year (e.g., 2023 for 2023/24 season) - current season if None
        status: SCHEDULED|LIVE|IN_PLAY|PAUSED|FINISHED|POSTPONED|SUSPENDED|CANCELLED
    """
    params = {"status": status}
    if season:
        params["season"] = str(season)
    
    return _get(f"/competitions/{code}/matches", params=params)


def get_team_matches(team_id: int, limit: int = 50, status: str = "FINISHED") -> Dict[str, Any]:
    """
    Fetch recent matches for a team.
    
    Args:
        team_id: Team ID from football-data.org
        limit: Max matches to return (1-100)
        status: Filter by status
    """
    params = {"limit": min(limit, 100), "status": status}
    return _get(f"/teams/{team_id}/matches", params=params)


# Top competitions available on free tier
FREE_TIER_COMPETITIONS = {
    "PL": "Premier League",
    "PD": "La Liga", 
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
    "CL": "Champions League",
    "EL": "Europa League",
    "EC": "European Championship",
    "WC": "World Cup",
}


def get_all_competitions() -> Dict[str, Any]:
    """Get list of all available competitions"""
    return _get("/competitions")
