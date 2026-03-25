"""
bot/providers/theodds_fixtures.py

TheOddsAPI mint elsődleges fixture forrás.
Előny: meccsek + odds egy API call-ban.
"""
import os
import datetime
from typing import List, Dict, Any
import requests

BASE_URL = "https://api.the-odds-api.com/v4"

# Top leagues sport keys
SPORT_KEYS = [
    "soccer_epl",  # Premier League
    "soccer_spain_la_liga",  # La Liga
    "soccer_germany_bundesliga",  # Bundesliga
    "soccer_italy_serie_a",  # Serie A
    "soccer_france_ligue_one",  # Ligue 1
    "soccer_uefa_champs_league",  # Champions League
    "soccer_uefa_europa_league",  # Europa League
    "soccer_uefa_europa_conference_league",  # Conference League
    "soccer_netherlands_eredivisie",  # Eredivisie
    "soccer_portugal_primeira_liga",  # Primeira Liga
    "soccer_scotland_premiership",  # Scottish Premiership
    "soccer_efl_champ",  # Championship
]

LEAGUE_NAMES = {
    "soccer_epl": "Premier League",
    "soccer_spain_la_liga": "La Liga",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "UEFA Champions League",
    "soccer_uefa_europa_league": "UEFA Europa League",
    "soccer_uefa_europa_conference_league": "UEFA Conference League",
    "soccer_netherlands_eredivisie": "Eredivisie",
    "soccer_portugal_primeira_liga": "Primeira Liga",
    "soccer_scotland_premiership": "Scottish Premiership",
    "soccer_efl_champ": "Championship",
}


def fetch_theodds_fixtures(date_str: str) -> List[Dict[str, Any]]:
    """
    Fetch fixtures from TheOddsAPI for a specific date.
    Returns matches with odds already included.
    """
    api_key = (os.getenv("ODDS_API_KEY") or "").strip()
    if not api_key:
        print("[TheOddsFixtures] ODDS_API_KEY not set!")
        return []

    # Parse date
    try:
        target_date = datetime.datetime.fromisoformat(date_str).date()
    except:
        print(f"[TheOddsFixtures] Invalid date: {date_str}")
        return []

    all_matches = []
    seen_ids = set()

    # Limit sport keys to avoid burning quota
    max_keys = int(os.getenv("ODDS_MAX_SPORT_KEYS", "6"))
    sport_keys = SPORT_KEYS[:max_keys]

    for sport_key in sport_keys:
        url = f"{BASE_URL}/sports/{sport_key}/odds"
        params = {
            "apiKey": api_key,
            "regions": os.getenv("ODDS_REGIONS", "eu"),
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }

        try:
            r = requests.get(url, params=params, timeout=25)
            if r.status_code != 200:
                print(f"[TheOddsFixtures] HTTP {r.status_code} for {sport_key}")
                continue

            events = r.json()
            if not isinstance(events, list):
                continue

            # Filter by date
            for event in events:
                commence_time = event.get("commence_time")
                if not commence_time:
                    continue

                try:
                    event_date = datetime.datetime.fromisoformat(commence_time.replace("Z", "+00:00")).date()
                except:
                    continue

                if event_date != target_date:
                    continue

                # Extract basic info
                event_id = event.get("id")
                if event_id in seen_ids:
                    continue
                seen_ids.add(event_id)

                home_team = event.get("home_team", "")
                away_team = event.get("away_team", "")

                if not home_team or not away_team:
                    continue

                # Extract best odds
                bookmakers = event.get("bookmakers", [])
                best_home = None
                best_draw = None
                best_away = None

                for bm in bookmakers:
                    for market in bm.get("markets", []):
                        if market.get("key") != "h2h":
                            continue

                        for outcome in market.get("outcomes", []):
                            name = (outcome.get("name") or "").lower()
                            price = outcome.get("price")

                            if price is None:
                                continue

                            try:
                                price = float(price)
                            except:
                                continue

                            home_norm = home_team.lower().replace(" ", "")
                            away_norm = away_team.lower().replace(" ", "")
                            name_norm = name.replace(" ", "")

                            if name == "draw" or name == "x":
                                best_draw = max(best_draw or 0, price)
                            elif home_norm in name_norm:
                                best_home = max(best_home or 0, price)
                            elif away_norm in name_norm:
                                best_away = max(best_away or 0, price)

                odds = {}
                if best_home and best_draw and best_away:
                    odds = {
                        "1": round(best_home, 2),
                        "X": round(best_draw, 2),
                        "2": round(best_away, 2),
                    }

                all_matches.append({
                    "sport": "football",
                    "fixture_id": hash(event_id) & 0x7FFFFFFF,
                    "league_name": LEAGUE_NAMES.get(sport_key, sport_key),
                    "country_name": "Europe",  # Could be enhanced
                    "kickoff_local": commence_time,
                    "home_team": home_team,
                    "away_team": away_team,
                    "odds": odds,
                    "odds_source": "theoddsapi",
                    "standings": {},
                    "injuries": [],
                    "source": "theodds",
                })

        except Exception as e:
            print(f"[TheOddsFixtures] Error fetching {sport_key}: {e}")
            continue

    print(f"[TheOddsFixtures] Fetched {len(all_matches)} matches for {date_str}")
    return all_matches
