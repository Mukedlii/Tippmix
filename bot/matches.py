import os
import datetime
from typing import Any, Dict, List, Tuple

import requests

SPORTS_API_KEY = os.getenv("SPORTS_API_KEY")
BASE_URL = "https://v3.football.api-sports.io"

# Ennyi meccset „gazdagon” elemzünk (form + gólátlag)
MAX_ENRICHED_FIXTURES = 10


def _api_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Egyszerű GET wrapper az api-football-hoz.
    """
    if not SPORTS_API_KEY:
        raise RuntimeError("SPORTS_API_KEY nincs beállítva.")

    url = BASE_URL + path
    headers = {
        "x-apisports-key": SPORTS_API_KEY,
    }

    resp = requests.get(url, headers=headers, params=params or {}, timeout=20)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"API JSON hiba: {repr(e)}")

    if data.get("errors"):
        # api-sports tipikus hiba mező
        raise RuntimeError(f"API error: {data['errors']}")

    return data


def _get_fixtures_for_today() -> List[Dict[str, Any]]:
    """
    Mai focimeccsek lekérése api-football-ból.
    Csak 'football' sport, napi dátum alapján.
    """
    today = datetime.date.today().isoformat()

    params = {
        "date": today,
        "timezone": "Europe/Budapest",
    }

    data = _api_get("/fixtures", params)
    fixtures = data.get("response", []) or []
    print(f"_get_fixtures_for_today: {len(fixtures)} raw fixture")

    return fixtures


def _get_team_stats(
    league_id: int,
    season: int,
    team_id: int,
    cache: Dict[Tuple[int, int, int], Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Egy csapat ligastatisztikája:
      - form (pl. 'WDWLW')
      - átlag lőtt gól (total)
      - átlag kapott gól (total)

    Cache-t használunk (league_id, season, team_id) kulcson,
    hogy ne hívjuk fölöslegesen az API-t.
    """
    key = (league_id, season, team_id)
    if key in cache:
        return cache[key]

    params = {
        "league": league_id,
        "season": season,
        "team": team_id,
    }

    try:
        data = _api_get("/teams/statistics", params)
    except Exception as e:
        print(f"_get_team_stats hiba (team={team_id}, league={league_id}):", repr(e))
        cache[key] = {}
        return cache[key]

    resp = data.get("response") or {}
    form = resp.get("form")  # pl. "WDWLW"
    goals = resp.get("goals") or {}
    goals_for = (goals.get("for") or {}).get("average") or {}
    goals_against = (goals.get("against") or {}).get("average") or {}

    def _to_float(x: Any) -> float | None:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        try:
            return float(str(x).replace(",", "."))
        except Exception:
            return None

    avg_for_total = _to_float(goals_for.get("total"))
    avg_against_total = _to_float(goals_against.get("total"))

    stats = {
        "form": form,  # pl. "WDWLW"
        "avg_goals_for": avg_for_total,
        "avg_goals_against": avg_against_total,
    }

    cache[key] = stats
    return stats


def fetch_matches_for_today() -> List[Dict[str, Any]]:
    """
    A main.py innen kapja a feldolgozott meccslistát.

    Egy elem például:

    {
      "sport": "football",
      "fixture_id": 123456,
      "league_name": "Premier League",
      "country_name": "England",
      "kickoff_local": "2025-12-06T20:00:00+01:00",
      "home_team": "Manchester United",
      "away_team": "West Ham",
      "home_form": "WDWLW",
      "away_form": "LLDWD",
      "home_avg_goals_for": 1.8,
      "home_avg_goals_against": 1.1,
      "away_avg_goals_for": 1.2,
      "away_avg_goals_against": 1.6,
    }

    Az AI ezeket az extra mezőket is látni fogja a promptban.
    """
    fixtures = _get_fixtures_for_today()
    matches: List[Dict[str, Any]] = []

    stats_cache: Dict[Tuple[int, int, int], Dict[str, Any]] = {}

    for idx, fx in enumerate(fixtures):
        fixture = fx.get("fixture") or {}
        league = fx.get("league") or {}
        teams = fx.get("teams") or {}

        fixture_id = fixture.get("id")
        kickoff = fixture.get("date")
        league_name = league.get("name")
        country_name = league.get("country")
        league_id = league.get("id")
        season = league.get("season")

        home = (teams.get("home") or {})
        away = (teams.get("away") or {})

        home_name = home.get("name")
        away_name = away.get("name")
        home_id = home.get("id")
        away_id = away.get("id")

        match: Dict[str, Any] = {
            "sport": "football",
            "fixture_id": fixture_id,
            "league_name": league_name,
            "country_name": country_name,
            "kickoff_local": kickoff,
            "home_team": home_name,
            "away_team": away_name,
        }

        # Az első MAX_ENRICHED_FIXTURES meccshez húzunk be extra statot.
        if (
            idx < MAX_ENRICHED_FIXTURES
            and league_id is not None
            and season is not None
            and home_id is not None
            and away_id is not None
        ):
            home_stats = _get_team_stats(league_id, season, home_id, stats_cache)
            away_stats = _get_team_stats(league_id, season, away_id, stats_cache)

            match["home_form"] = home_stats.get("form")
            match["home_avg_goals_for"] = home_stats.get("avg_goals_for")
            match["home_avg_goals_against"] = home_stats.get("avg_goals_against")

            match["away_form"] = away_stats.get("form")
            match["away_avg_goals_for"] = away_stats.get("avg_goals_for")
            match["away_avg_goals_against"] = away_stats.get("avg_goals_against")

        matches.append(match)

    print(f"fetch_matches_for_today: {len(matches)} meccs, "
          f"{min(len(matches), MAX_ENRICHED_FIXTURES)} extra statisztikával.")

    return matches
