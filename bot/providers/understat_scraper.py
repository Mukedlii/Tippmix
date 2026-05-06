"""
bot/providers/understat_scraper.py

Understat.com — INGYENES xG + historikus meccs adatok

MIT AD:
  - xG (Expected Goals) minden meccshez
  - Gólszámok, eredmények
  - Csapat formák
  - TOP 5 európai liga: EPL, La Liga, Bundesliga, Serie A, Ligue 1

MIÉRT HASZNOS:
  - Az xG segíti a bot döntéseit (nemcsak gólátlag, hanem "mennyi gólt kellett volna lőni")
  - Ingyenes, nincs API kulcs, csak JSON scraping
  - Visszamenőleg 2014-ig elérhető

ADATBÁZIS INTEGRÁCIÓ:
  - Menti a results táblába a gólszámokat (ha még nincs meg)
  - Külön tárolja az xG értékeket (opcionálisan)
"""

from __future__ import annotations

import os
import re
import json
import time
import sqlite3
import datetime
import logging
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "https://understat.com"

LEAGUE_MAP = {
    "EPL":         ("Premier League", "England", 9001),
    "La_liga":     ("La Liga", "Spain", 9002),
    "Bundesliga":  ("Bundesliga", "Germany", 9003),
    "Serie_A":     ("Serie A", "Italy", 9004),
    "Ligue_1":     ("Ligue 1", "France", 9005),
    "RFPL":        ("Russian Premier League", "Russia", 9006),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://understat.com/",
}


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_db_path()) or ".", exist_ok=True)
    con = sqlite3.connect(_db_path())
    con.execute("PRAGMA journal_mode=WAL;")
    return con


def _get(url: str) -> Optional[str]:
    try:
        time.sleep(2.0)
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            return r.text
        log.warning(f"Understat HTTP {r.status_code}: {url}")
    except Exception as e:
        log.error(f"Understat fetch hiba {url}: {e}")
    return None


def _parse_json_var(html: str, var_name: str) -> Optional[Any]:
    """Kinyeri a JSON adatot az Understat HTML-éből (JSON.parse beágyazva)."""
    try:
        pattern = rf"var\s+{var_name}\s*=\s*JSON\.parse\('(.+?)'\)"
        match = re.search(pattern, html, re.DOTALL)
        if match:
            encoded = match.group(1)
            # Understat kódolás
            decoded = encoded.encode().decode("unicode_escape")
            return json.loads(decoded)
    except Exception as e:
        log.debug(f"JSON parse hiba ({var_name}): {e}")
    return None


def fetch_league_season(
    league_key: str,
    season_year: int,
) -> List[Dict[str, Any]]:
    """
    Egy liga egy szezonjának összes meccsét lekéri Understat-ról.

    Args:
        league_key: pl. "EPL", "La_liga", "Bundesliga"
        season_year: pl. 2023 (= 2023/24 szezon)

    Returns:
        Lista meccsekkel (gólok + xG értékek)
    """
    league_info = LEAGUE_MAP.get(league_key)
    if not league_info:
        log.error(f"Ismeretlen liga: {league_key}")
        return []

    league_name, country, league_id = league_info
    url = f"{BASE_URL}/league/{league_key}/{season_year}"

    print(f"[Understat] Letöltés: {league_name} {season_year}...")
    html = _get(url)
    if not html:
        return []

    dates_data = _parse_json_var(html, "datesData")
    if not dates_data:
        log.warning(f"Nem sikerült kinyerni: datesData ({league_key} {season_year})")
        return []

    matches = []
    for match in dates_data:
        try:
            match_id = match.get("id")
            home_team = match.get("h", {})
            away_team = match.get("a", {})

            home_goals = match.get("goals", {}).get("h")
            away_goals = match.get("goals", {}).get("a")
            home_xg = match.get("xG", {}).get("h")
            away_xg = match.get("xG", {}).get("a")

            if home_goals is None or away_goals is None:
                continue

            status = "FT" if match.get("isResult") else "SCHEDULED"
            if status != "FT":
                continue

            matches.append({
                "id": match_id,
                "home_team": home_team.get("title"),
                "away_team": away_team.get("title"),
                "home_team_id": int(f"90{abs(hash(home_team.get('title','')))}") % 1000000,
                "away_team_id": int(f"90{abs(hash(away_team.get('title','')))}") % 1000000,
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "home_xg": float(home_xg) if home_xg else None,
                "away_xg": float(away_xg) if away_xg else None,
                "date": match.get("datetime", "")[:10],
                "league_id": league_id,
                "league_name": league_name,
                "season": season_year,
                "source": "understat",
            })
        except Exception as e:
            log.debug(f"Meccs parse hiba: {e}")

    print(f"[Understat] ✅ {league_name} {season_year}: {len(matches)} meccs kinyerve")
    return matches


def save_to_database(matches: List[Dict[str, Any]]) -> int:
    """Menti a meccseket az adatbázisba (results tábla)."""
    if not matches:
        return 0

    con = _connect()
    now_iso = datetime.datetime.utcnow().isoformat()
    stored = 0

    try:
        for m in matches:
            home_g = m.get("home_goals")
            away_g = m.get("away_goals")
            if home_g is None or away_g is None:
                continue

            if home_g > away_g:
                result = "1"
            elif home_g < away_g:
                result = "2"
            else:
                result = "X"

            # Understat-nak nincs fixture_id a mi rendszerünkkel kompatibilisen
            # Generálunk egyet a csapatnév + dátum alapján
            date_str = m.get("date", "")
            fake_fid = abs(hash(f"understat_{m.get('home_team','')}_{m.get('away_team','')}_{date_str}")) % 9000000 + 1000000

            con.execute("""
                INSERT INTO results
                    (fixture_id, final_score, result_1x2, status, updated_ts_utc, raw_json,
                     home_goals, away_goals, home_team_id, away_team_id, league_id, season)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    final_score = excluded.final_score,
                    result_1x2 = excluded.result_1x2,
                    home_goals = excluded.home_goals,
                    away_goals = excluded.away_goals,
                    home_team_id = excluded.home_team_id,
                    away_team_id = excluded.away_team_id,
                    league_id = excluded.league_id,
                    season = excluded.season,
                    updated_ts_utc = excluded.updated_ts_utc
            """, (
                fake_fid,
                f"{home_g}-{away_g}",
                result,
                "FT",
                now_iso,
                json.dumps({"home": m.get("home_team"), "away": m.get("away_team"),
                            "home_xg": m.get("home_xg"), "away_xg": m.get("away_xg"),
                            "date": date_str, "source": "understat"}, ensure_ascii=False),
                home_g,
                away_g,
                m.get("home_team_id"),
                m.get("away_team_id"),
                m.get("league_id"),
                m.get("season"),
            ))
            stored += 1

        con.commit()
    finally:
        con.close()

    return stored


def build_understat_database(
    leagues: Optional[List[str]] = None,
    seasons_back: int = 3,
) -> Dict[str, int]:
    """
    Understat historikus adatbázis feltöltése.

    Args:
        leagues: Liga kulcsok listája (None = összes)
        seasons_back: Hány szezonra menjen vissza

    Returns:
        Dict: {liga: tárolt meccsek száma}
    """
    if leagues is None:
        leagues = list(LEAGUE_MAP.keys())[:5]  # TOP 5 alapértelmezetten (RFPL nélkül)

    current_year = datetime.date.today().year
    results: Dict[str, int] = {}

    for league in leagues:
        total = 0
        for offset in range(seasons_back, -1, -1):
            season = current_year - offset - 1
            matches = fetch_league_season(league, season)
            stored = save_to_database(matches)
            total += stored
            print(f"  → {stored} meccs mentve ({league} {season})")
        results[league] = total
        print(f"[Understat] {league}: {total} meccs összesen\n")

    return results


def get_team_xg_form(team_name: str, league_key: str, season_year: int) -> Optional[Dict]:
    """
    Egy csapat aktuális xG formáját kéri le (utolsó 5 meccs).
    Hasznos a napi tippekhez.
    """
    matches = fetch_league_season(league_key, season_year)
    team_matches = [
        m for m in matches
        if (m.get("home_team") or "").lower() == team_name.lower()
        or (m.get("away_team") or "").lower() == team_name.lower()
    ]

    if not team_matches:
        return None

    last5 = team_matches[-5:]
    home_xg_avg = 0.0
    away_xg_avg = 0.0
    n = len(last5)
    for m in last5:
        if m.get("home_team", "").lower() == team_name.lower():
            home_xg_avg += float(m.get("home_xg") or 0)
        else:
            away_xg_avg += float(m.get("away_xg") or 0)

    return {
        "team": team_name,
        "matches": n,
        "avg_xg_scored": (home_xg_avg + away_xg_avg) / n if n > 0 else 0,
        "recent_matches": last5,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    seasons = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    build_understat_database(seasons_back=seasons)
