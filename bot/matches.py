
from datetime import datetime
import os
import requests


BASE_URL = "https://v3.football.api-sports.io"

# Top ligák példaként – ezt nyugodtan módosíthatod:
# 39 = Premier League, 140 = La Liga, 135 = Serie A, 78 = Bundesliga, 61 = Ligue 1
TOP_LEAGUES = [39, 140, 135, 78, 61]


def _api_get(endpoint: str, params: dict) -> dict:
    """Segédfüggvény az API híváshoz (API-FOOTBALL / API-Sports)."""
    api_key = os.getenv("SPORT_API_KEY")
    if not api_key:
        raise RuntimeError("Hiányzik a SPORT_API_KEY környezeti változó (API-Sports / API-Football kulcs).")

    url = f"{BASE_URL}{endpoint}"
    headers = {
        "x-apisports-key": api_key,
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _get_fixtures_for_today():
    """Mai napi focimeccsek lekérése a kiválasztott ligákból."""
    today = datetime.utcnow().date().isoformat()

    all_fixtures = []

    for league_id in TOP_LEAGUES:
        data = _api_get(
            "/fixtures",
            {
                "date": today,
                "league": league_id,
                "season": datetime.utcnow().year,
                "timezone": "Europe/Budapest",
            },
        )
        fixtures = data.get("response", [])
        all_fixtures.extend(fixtures)

    return all_fixtures


def _get_odds_for_fixture(fixture_id: int):
    """Odds lekérés egy konkrét meccsre. Visszaad (home, draw, away) decimális oddsként vagy None."""
    data = _api_get(
        "/odds",
        {
            "fixture": fixture_id,
        },
    )
    resp = data.get("response", [])
    if not resp:
        return None, None, None

    bookmakers = resp[0].get("bookmakers", [])
    if not bookmakers:
        return None, None, None

    home_odd = draw_odd = away_odd = None

    for bet in bookmakers[0].get("bets", []):
        name = (bet.get("name") or "").lower()
        if "winner" in name or "1x2" in name:
            for val in bet.get("values", []):
                label = (val.get("value") or "").lower()
                odd_str = val.get("odd")
                try:
                    odd_val = float(odd_str) if odd_str is not None else None
                except ValueError:
                    odd_val = None

                if "home" in label or label == "1":
                    home_odd = odd_val
                elif "draw" in label or label == "x":
                    draw_odd = odd_val
                elif "away" in label or label == "2":
                    away_odd = odd_val
            break

    return home_odd, draw_odd, away_odd


def fetch_matches_for_today():
    """Fő függvény, amit a bot használ: mai meccsek + odds alapú struktúra."""
    fixtures = _get_fixtures_for_today()
    results = []

    for fx in fixtures:
        fixture = fx.get("fixture", {})
        teams = fx.get("teams", {})
        league = fx.get("league", {})

        fixture_id = fixture.get("id")
        if fixture_id is None:
            continue

        home_team = teams.get("home", {}).get("name")
        away_team = teams.get("away", {}).get("name")

        home_odd, draw_odd, away_odd = _get_odds_for_fixture(fixture_id)

        if home_odd is None or away_odd is None:
            continue

        result = {
            "id": fixture_id,
            "league": league.get("name") or "Ismeretlen liga",
            "home": home_team or "Hazai",
            "away": away_team or "Vendég",
            "start_time": fixture.get("date"),
            "odds": {
                "home": home_odd,
                "draw": draw_odd,
                "away": away_odd,
            },
            "stats": {
                "note": "Alapadatok API-FOOTBALL-ból. Részletes statok később.",
            },
        }
        results.append(result)

    return results
