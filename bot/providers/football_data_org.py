"""
bot/providers/football_data_org.py

Football-data.org ingyenes API — AJÁNLOTT FŐ FORRÁS

MIÉRT AJÁNLOTT:
  - Teljesen ingyenes (csak regisztráció kell, kártya NEM)
  - 10 req/perc limit (bőven elég)
  - Visszamenőleg 5+ szezon historikus adat
  - Pontos gólszámok, csapat ID-k, liga ID-k
  - TOP 12 európai liga + UCL/UEL

INGYENES LIGÁK:
  PL  = Premier League (Anglia)
  BL1 = Bundesliga (Németország)
  SA  = Serie A (Olaszország)
  PD  = La Liga (Spanyolország)
  FL1 = Ligue 1 (Franciaország)
  DED = Eredivisie (Hollandia)
  PPL = Primeira Liga (Portugália)
  CL  = Champions League
  EL  = Europa League
  EC  = Eb (Európa-bajnokság)
  WC  = Vb (Világbajnokság)

REGISZTRÁCIÓ (INGYENES):
  https://www.football-data.org/client/register

BEÁLLÍTÁS:
  GitHub Secret: FOOTBALL_DATA_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Anélkül is fut: 10 req/perc limit érvényes marad, de autentikáció nélkül
néhány endpoint korlátozott lehet.
"""

from __future__ import annotations

import os
import time
import sqlite3
import datetime
import logging
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"

# Ingyenes ligák (regisztráció után elérhetők)
FREE_COMPETITIONS = {
    "PL":  ("Premier League", "England", 2021),
    "BL1": ("Bundesliga", "Germany", 2002),
    "SA":  ("Serie A", "Italy", 2019),
    "PD":  ("La Liga", "Spain", 2014),
    "FL1": ("Ligue 1", "France", 2015),
    "DED": ("Eredivisie", "Netherlands", 2003),
    "PPL": ("Primeira Liga", "Portugal", 2017),
    "CL":  ("Champions League", "Europe", 2001),
    "EL":  ("Europa League", "Europe", 2018),
}

# Magyar/Kelet-európai ligák (fizetős tier, de ellenőrizhető)
EXTRA_COMPETITIONS: Dict[str, tuple] = {}

# Mennyi szezonra megy vissza (alapértelmezett: 3 szezon)
DEFAULT_SEASONS_BACK = int(os.getenv("FD_SEASONS_BACK", "3"))


def _headers() -> Dict[str, str]:
    key = (os.getenv("FOOTBALL_DATA_API_KEY") or "").strip()
    h = {"X-Auth-Token": key} if key else {}
    return h


def _get(path: str, params: Dict[str, Any] | None = None) -> Optional[Dict]:
    url = f"{BASE_URL}{path}"
    try:
        time.sleep(6.5)  # 10 req/perc = 1 req/6s → biztonságos
        r = requests.get(url, headers=_headers(), params=params or {}, timeout=20)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            log.warning("Rate limit, várakozás 60s...")
            time.sleep(60)
            r = requests.get(url, headers=_headers(), params=params or {}, timeout=20)
            return r.json() if r.status_code == 200 else None
        log.warning(f"football-data.org HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"football-data.org hiba {url}: {e}")
    return None


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def _connect() -> sqlite3.Connection:
    import os as _os
    _os.makedirs(os.path.dirname(_db_path()) or ".", exist_ok=True)
    con = sqlite3.connect(_db_path())
    con.execute("PRAGMA journal_mode=WAL;")
    return con


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL UNIQUE,
            final_score TEXT,
            result_1x2 TEXT,
            status TEXT,
            updated_ts_utc TEXT NOT NULL,
            raw_json TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_team_id INTEGER,
            away_team_id INTEGER,
            league_id INTEGER,
            season INTEGER
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_results_league ON results(league_id);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_results_home_team ON results(home_team_id);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_results_away_team ON results(away_team_id);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_results_season ON results(season);")
    con.commit()


def _upsert_match(con: sqlite3.Connection, match: Dict[str, Any], league_id: int, season: int) -> bool:
    """Egy meccs eredményének tárolása/frissítése az adatbázisban."""
    import json

    fid = match.get("id")
    if not fid:
        return False

    score = match.get("score", {})
    ft = score.get("fullTime", {})
    home_g = ft.get("home")
    away_g = ft.get("away")

    if home_g is None or away_g is None:
        return False  # Nincs végeredmény

    # 1X2 eredmény
    if home_g > away_g:
        result = "1"
    elif home_g < away_g:
        result = "2"
    else:
        result = "X"

    status = match.get("status", "")
    # Csak lezárt meccsek
    if status not in ("FINISHED",):
        return False

    home_team = match.get("homeTeam", {})
    away_team = match.get("awayTeam", {})
    home_id = home_team.get("id")
    away_id = away_team.get("id")

    kickoff = match.get("utcDate", "")[:10]

    now_iso = datetime.datetime.utcnow().isoformat()

    con.execute("""
        INSERT INTO results
            (fixture_id, final_score, result_1x2, status, updated_ts_utc, raw_json,
             home_goals, away_goals, home_team_id, away_team_id, league_id, season)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fixture_id) DO UPDATE SET
            final_score = excluded.final_score,
            result_1x2 = excluded.result_1x2,
            status = excluded.status,
            updated_ts_utc = excluded.updated_ts_utc,
            home_goals = excluded.home_goals,
            away_goals = excluded.away_goals,
            home_team_id = excluded.home_team_id,
            away_team_id = excluded.away_team_id,
            league_id = excluded.league_id,
            season = excluded.season
    """, (
        fid,
        f"{home_g}-{away_g}",
        result,
        "FT",
        now_iso,
        json.dumps({"home": home_team.get("name"), "away": away_team.get("name"),
                    "date": kickoff, "score": f"{home_g}-{away_g}"}, ensure_ascii=False),
        int(home_g),
        int(away_g),
        int(home_id) if home_id else None,
        int(away_id) if away_id else None,
        int(league_id),
        int(season),
    ))
    return True


def fetch_competition_season(competition_code: str, season_year: int) -> int:
    """
    Egy liga egy szezonjának összes meccsét letölti és tárolja.

    Args:
        competition_code: pl. "PL", "BL1", "SA"
        season_year: Szezon kezdő éve (pl. 2023 = 2023/24)

    Returns:
        Tárolt meccsek száma
    """
    comp_info = FREE_COMPETITIONS.get(competition_code, (competition_code, "Unknown", None))
    league_name, country, league_api_id = comp_info
    # football-data.org competition ID-jét a path-ban használjuk
    league_id = league_api_id or hash(competition_code) % 10000

    print(f"[FD] Letöltés: {league_name} {season_year}/{season_year+1}...")

    data = _get(f"/competitions/{competition_code}/matches", {"season": str(season_year)})
    if not data:
        print(f"[FD] ❌ Nem sikerült: {competition_code} {season_year}")
        return 0

    matches = data.get("matches", [])
    if not matches:
        print(f"[FD] Üres szezon: {competition_code} {season_year}")
        return 0

    con = _connect()
    _ensure_schema(con)

    stored = 0
    skipped = 0
    for m in matches:
        try:
            if _upsert_match(con, m, league_id, season_year):
                stored += 1
            else:
                skipped += 1
        except Exception as e:
            log.error(f"DB hiba: {e}")

    con.commit()
    con.close()

    print(f"[FD] ✅ {league_name} {season_year}: {stored} meccs tárolva ({skipped} kihagyva)")
    return stored


def build_historical_database(
    competitions: Optional[List[str]] = None,
    seasons_back: int = DEFAULT_SEASONS_BACK,
) -> Dict[str, int]:
    """
    Teljes historikus adatbázis feltöltése.

    Args:
        competitions: Liga kódok listája (None = összes ingyenes liga)
        seasons_back: Hány szezonra menjen vissza

    Returns:
        Dict: {liga_kód: tárolt meccsek száma}
    """
    if competitions is None:
        competitions = list(FREE_COMPETITIONS.keys())

    current_year = datetime.date.today().year
    results: Dict[str, int] = {}

    total = 0
    for comp in competitions:
        comp_total = 0
        for season_offset in range(seasons_back, -1, -1):
            season_year = current_year - season_offset - 1
            count = fetch_competition_season(comp, season_year)
            comp_total += count
        results[comp] = comp_total
        total += comp_total
        print(f"[FD] {comp}: összesen {comp_total} meccs tárolva")

    print(f"\n[FD] === ÖSSZESÍTŐ ===")
    print(f"[FD] Összes tárolt meccs: {total}")
    for comp, cnt in results.items():
        print(f"  {comp}: {cnt}")

    return results


def get_todays_fixtures(competition_code: str) -> List[Dict[str, Any]]:
    """
    Mai meccsek lekérése (élő + közelgő).

    Returns:
        Lista meccsekkel: home_team, away_team, kickoff, league_id, fixture_id
    """
    data = _get(f"/competitions/{competition_code}/matches", {
        "dateFrom": datetime.date.today().isoformat(),
        "dateTo": datetime.date.today().isoformat(),
        "status": "SCHEDULED,TIMED",
    })
    if not data:
        return []

    comp_info = FREE_COMPETITIONS.get(competition_code, (competition_code, "Unknown", None))
    league_name, country, league_id = comp_info

    out = []
    for m in data.get("matches", []):
        home = m.get("homeTeam", {})
        away = m.get("awayTeam", {})
        out.append({
            "fixture_id": m.get("id"),
            "home_team": home.get("name") or home.get("shortName"),
            "away_team": away.get("name") or away.get("shortName"),
            "home_team_id": home.get("id"),
            "away_team_id": away.get("id"),
            "league_id": league_id,
            "league_name": league_name,
            "country_name": country,
            "kickoff": m.get("utcDate", ""),
            "source": "football-data.org",
        })
    return out


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1 and sys.argv[1] == "today":
        # Mai meccsek mutatása
        for code in list(FREE_COMPETITIONS.keys())[:5]:
            fixtures = get_todays_fixtures(code)
            if fixtures:
                print(f"\n{code}:")
                for f in fixtures:
                    print(f"  {f['home_team']} vs {f['away_team']} ({f['kickoff'][:16]})")
    else:
        # Teljes historikus feltöltés
        seasons = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEASONS_BACK
        build_historical_database(seasons_back=seasons)
