import os
import time
from typing import Any, Dict, List, Optional

import requests

from bot.api_keys import get_sportsdataio_key


BASE_URL = os.getenv("SPORTSDATAIO_BASE_URL", "https://api.sportsdata.io/v3/soccer/scores/json").rstrip("/")


def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Any:
    key = get_sportsdataio_key()
    url = f"{BASE_URL}{path}"
    params = dict(params or {})
    params["key"] = key

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"SportsDataIO HTTP {r.status_code}: {r.text[:600]}")
            data = r.json()
            return data
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"SportsDataIO request failed: {repr(last_err)}")


def fetch_games_by_date(date_yyyy_mm_dd: str) -> List[Dict[str, Any]]:
    data = _get(f"/GamesByDate/{date_yyyy_mm_dd}")
    if isinstance(data, list):
        return data
    return data.get("data") or []


def fetch_game_by_id(game_id: int) -> Optional[Dict[str, Any]]:
    data = _get(f"/Game/{int(game_id)}")
    if isinstance(data, dict):
        return data
    return None


def normalize_game(game: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fixture_id = game.get("GameId") or game.get("GlobalGameId")
    if fixture_id is None:
        return None

    home = game.get("HomeTeamName") or game.get("HomeTeam") or "Hazai"
    away = game.get("AwayTeamName") or game.get("AwayTeam") or "Vendég"
    kickoff = game.get("DateTime") or game.get("Day") or ""
    league = game.get("CompetitionName") or game.get("League") or "Ismeretlen liga"
    country = game.get("Country") or ""

    return {
        "sport": "football",
        "fixture_id": int(fixture_id),
        "league_name": str(league),
        "country_name": str(country),
        "kickoff_local": str(kickoff),
        "home_team": str(home),
        "away_team": str(away),
        "odds": {},
        "standings": {},
        "injuries": [],
    }
