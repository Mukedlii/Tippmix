import os
import datetime
from typing import List, Dict, Any

import requests

SPORT_API_KEY = os.getenv("SPORT_API_KEY")

# API-Sports base URL-ek
FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
BASKETBALL_BASE_URL = "https://v1.basketball.api-sports.io"

# Top fociligák (API-FOOTBALL league ID-k)
# Premier League, La Liga, Serie A, Bundesliga, Ligue 1
FOOTBALL_LEAGUES = [39, 140, 135, 78, 61]

# Kosár: NBA (API-BASKETBALL league ID, pl. 12)
BASKETBALL_LEAGUES = [12]


class ApiSportsError(RuntimeError):
    pass


def _api_get(base_url: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Egységes GET wrapper az API-SPORTS-hoz.
    """
    if not SPORT_API_KEY:
        raise ApiSportsError("Hiányzik a SPORT_API_KEY környezeti változó.")

    headers = {
        "x-apisports-key": SPORT_API_KEY,
    }

    url = base_url.rstrip("/") + path
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    if data.get("errors"):
        # API-Sports saját hiba mező
        raise ApiSportsError(f"API hiba: {data['errors']}")

    return data


def _season_for_european_leagues(today: datetime.date) -> int:
    """
    Az európai fociligáknál a szezon egy évszám (pl. 2024 -> 2024/2025 szezon).
    """
    year = today.year
    if today.month < 7:
        return year - 1
    return year


def _get_football_matches_for_date(date_str: str) -> List[Dict[str, Any]]:
    """
    Mai focimeccsek lekérése a top ligákból.
    """
    today = datetime.date.fromisoformat(date_str)
    season = _season_for_european_leagues(today)

    matches: List[Dict[str, Any]] = []

    for league_id in FOOTBALL_LEAGUES:
        try:
            data = _api_get(
                FOOTBALL_BASE_URL,
                "/fixtures",
                {
                    "date": date_str,
                    "league": league_id,
                    "season": season,
                },
            )
        except Exception as e:
            print(f"Foci league {league_id} lekérés hiba: {repr(e)}")
            continue

        for item in data.get("response", []):
            fixture = item.get("fixture", {})
            league = item.get("league", {})
            teams = item.get("teams", {})

            home_team = teams.get("home", {}).get("name")
            away_team = teams.get("away", {}).get("name")
            fixture_id = fixture.get("id")
            start_time = fixture.get("date")

            if not home_team or not away_team or not fixture_id:
                continue

            match = {
                "id": f"football-{fixture_id}",
                "sport": "football",
                "league": league.get("name"),
                "country": league.get("country"),
                "home": home_team,
                "away": away_team,
                "start_time": start_time,
                # Egyszerűsítés: odds-ot most nem kérünk külön az API-ból,
                # így kevesebb request fogy. Az OpenAI statok alapján dönt.
                "odds": {
                    "home": None,
                    "away": None,
                    "draw": None,
                },
                "stats": {
                    "league_id": league_id,
                    "season": season,
                },
            }
            matches.append(match)

    return matches


def _get_basketball_matches_for_date(date_str: str) -> List[Dict[str, Any]]:
    """
    Mai kosármeccsek (pl. NBA) lekérése.
    """
    matches: List[Dict[str, Any]] = []

    for league_id in BASKETBALL_LEAGUES:
        try:
            data = _api_get(
                BASKETBALL_BASE_URL,
                "/games",
                {
                    "date": date_str,
                    "league": league_id,
                    # season opcionális, ezért most elhagyjuk,
                    # hogy ne kelljen évente frissíteni.
                },
            )
        except Exception as e:
            print(f"Kosár league {league_id} lekérés hiba: {repr(e)}")
            continue

        for item in data.get("response", []):
            league = item.get("league", {})
            teams = item.get("teams", {})
            home_team = teams.get("home", {}).get("name")
            away_team = teams.get("away", {}).get("name")
            game_id = item.get("id") or item.get("game", {}).get("id")
            start_time = item.get("date")

            if not home_team or not away_team or not game_id:
                continue

            match = {
                "id": f"basketball-{game_id}",
                "sport": "basketball",
                "league": league.get("name"),
                "country": league.get("country"),
                "home": home_team,
                "away": away_team,
                "start_time": start_time,
                "odds": {
                    # Itt most nem kérünk külön odds-ot, az OpenAI elbír nélküle is.
                    "home": None,
                    "away": None,
                    "draw": None,
                },
                "stats": {
                    "league_id": league_id,
                },
            }
            matches.append(match)

    return matches


def fetch_matches_for_today() -> List[Dict[str, Any]]:
    """
    Összegyűjti a mai foci + kosár meccseket.
    """
    today = datetime.datetime.utcnow().date()
    date_str = today.isoformat()
    print(f"Meccsek lekérése erre a napra: {date_str}")

    all_matches: List[Dict[str, Any]] = []

    football_matches = _get_football_matches_for_date(date_str)
    print(f"Foci meccsek: {len(football_matches)}")
    all_matches.extend(football_matches)

    basketball_matches = _get_basketball_matches_for_date(date_str)
    print(f"Kosár meccsek: {len(basketball_matches)}")
    all_matches.extend(basketball_matches)

    print(f"Összesített meccsszám (multi-sport): {len(all_matches)}")
    return all_matches
