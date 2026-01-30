import os
import re
import datetime
from typing import Any, Dict, List, Optional

import requests

from bot.api_keys import get_api_sports_key, resolve_sports_provider
from bot.odds import fetch_api_football_1x2_odds
from bot.providers import sportsdataio
from bot.providers import theoddsapi

TZ = os.getenv("TIPPMIX_TIMEZONE", "Europe/Budapest")

MAX_FIXTURES = int(os.getenv("TIPPMIX_MAX_FIXTURES", "200"))
ODDS_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_ODDS_LOOKUP_LIMIT", "120"))

# minimumok (hogy matches.py is tudja, mennyi meccs kell minimum a poolhoz)
MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))

# mennyire terjesszük ki a keresést "ma + hány napra előre", ha kevés a meccs
# Profi ajánlás fizetős csatornához: maradjunk az adott napnál (0), és csak akkor engedjünk egzotikus ligákat,
# ha nem jön ki a minimum pool.
MAX_DAYS_AHEAD = int(os.getenv("TIPPMIX_MAX_DAYS_AHEAD", "0"))

# mekkora legyen minimum a pool (slot után számolva)
# ha nincs beállítva, számoljuk: VIP+FREE+12 (hogy legyen miből válogatni)
MIN_POOL = int(os.getenv("TIPPMIX_MIN_POOL", str(MIN_VIP + MIN_FREE + 12)))

TOP_LEAGUE_KEYWORDS = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "UEFA Champions League", "Champions League",
    "UEFA Europa League", "Europa League",
    "UEFA Europa Conference League", "Conference League",
    "Eredivisie", "Primeira Liga", "Scottish Premiership",
    "FA Cup", "Copa del Rey", "DFB Pokal", "Coppa Italia",
]

# The Odds API sport_key mapping (best-effort). Can be overridden by env ODDS_SPORT_KEYS.
LEAGUE_TO_THEODDS_KEY = {
    "premier league": "soccer_epl",
    "la liga": "soccer_spain_la_liga",
    "serie a": "soccer_italy_serie_a",
    "bundesliga": "soccer_germany_bundesliga",
    "ligue 1": "soccer_france_ligue_one",
    "eredivisie": "soccer_netherlands_eredivisie",
    "primeira liga": "soccer_portugal_primeira_liga",
    "scottish premiership": "soccer_scotland_premiership",
    "champions league": "soccer_uefa_champs_league",
    "europa league": "soccer_uefa_europa_league",
    "conference league": "soccer_uefa_europa_conference_league",
}

YOUTH_PATTERNS = [
    r"\bU\d{2}\b", r"\bU-?\d{2}\b", r"\bYouth\b", r"\bReserve\b", r"\bB Team\b",
    r"\bPrimavera\b", r"\bU23\b", r"\bU21\b", r"\bU20\b", r"\bU19\b",
]

FRIENDLY_PATTERNS = [r"friendly", r"barátságos"]


def _api_get(path: str, params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    url = f"https://v3.football.api-sports.io/{path.lstrip('/')}"
    headers = {"x-apisports-key": get_api_sports_key()}
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"API error {r.status_code}: {r.text[:300]}")
    return r.json() or {}


def _extract_hour(iso: str) -> Optional[int]:
    if not iso or "T" not in iso:
        return None
    try:
        return int(iso.split("T")[1][:2])
    except Exception:
        return None


def _slot_filter(matches: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()
    out: List[Dict[str, Any]] = []
    for m in matches:
        h = _extract_hour(str(m.get("kickoff_local") or ""))
        if h is None:
            out.append(m)
            continue
        if slot == "DAY":
            if 9 <= h < 16:
                out.append(m)
        else:
            if 16 <= h <= 23:
                out.append(m)
    return out


def _is_youth(match: Dict[str, Any]) -> bool:
    txt = f"{match.get('league_name','')} {match.get('home_team','')} {match.get('away_team','')}"
    for p in YOUTH_PATTERNS:
        if re.search(p, txt, flags=re.IGNORECASE):
            return True
    return False


def _is_friendly(match: Dict[str, Any]) -> bool:
    txt = f"{match.get('league_name','')}"
    for p in FRIENDLY_PATTERNS:
        if re.search(p, txt, flags=re.IGNORECASE):
            return True
    return False


def _is_top_match(match: Dict[str, Any]) -> bool:
    league = str(match.get("league_name") or "")
    for k in TOP_LEAGUE_KEYWORDS:
        if k.lower() in league.lower():
            return True
    return False


def _rank_bucket(match: Dict[str, Any]) -> int:
    """
    0 = top / komoly felnőtt
    1 = felnőtt (nem top), nem youth, nem friendly  ("exotic")
    2 = youth
    3 = friendly
    """
    if _is_friendly(match):
        return 3
    if _is_top_match(match) and not _is_youth(match):
        return 0
    if not _is_youth(match):
        return 1
    return 2


def _theodds_sport_keys_for_matches(matches: List[Dict[str, Any]]) -> List[str]:
    env = (os.getenv("ODDS_SPORT_KEYS") or "").strip()
    if env:
        keys = [k.strip() for k in env.split(",") if k.strip()]
        return keys

    # derive from leagues present in the pool
    keys: List[str] = []
    for m in matches:
        league = (m.get("league_name") or "").lower()
        for k, sk in LEAGUE_TO_THEODDS_KEY.items():
            if k in league and sk not in keys:
                keys.append(sk)
    return keys


def _enrich_odds_from_theoddsapi(matches: List[Dict[str, Any]]) -> None:
    """Best-effort odds enrichment for SportsDataIO runs using The Odds API.

    Budgeted by ODDS_MAX_REQUESTS_PER_RUN (default 6). Each sport_key query costs 1 request.
    """
    api_key = (os.getenv("ODDS_API_KEY") or "").strip()
    if not api_key:
        return

    try:
        max_req = int(os.getenv("ODDS_MAX_REQUESTS_PER_RUN", "6"))
    except Exception:
        max_req = 6

    sport_keys = _theodds_sport_keys_for_matches(matches)
    if not sport_keys:
        return

    # cap number of sport_key calls
    sport_keys = sport_keys[: max(0, max_req)]

    # First ensure events are fetched (1 request per sport_key)
    for sk in sport_keys:
        try:
            theoddsapi.fetch_odds_for_sport_key(sk)
        except Exception:
            continue

    # Then match and enrich
    enriched = 0
    for m in matches:
        odds = m.get("odds") or {}
        if odds.get("1") and odds.get("X") and odds.get("2"):
            continue

        o1, ox, o2 = theoddsapi.get_1x2_for_match(m.get("home_team") or "", m.get("away_team") or "", sport_keys)
        if o1 and ox and o2:
            m["odds"] = {"1": float(o1), "X": float(ox), "2": float(o2)}
            m["odds_source"] = "theoddsapi"
            enriched += 1

    if enriched:
        print(f"[matches] theoddsapi enriched odds for {enriched} matches (sport_keys={len(sport_keys)})")


def _fetch_fixtures_for_date(date_str: str) -> List[Dict[str, Any]]:
    provider = resolve_sports_provider()
    if provider == "sportsdataio":
        games = sportsdataio.fetch_games_by_date(date_str)
        out: List[Dict[str, Any]] = []
        for game in games[:MAX_FIXTURES]:
            item = sportsdataio.normalize_game(game)
            if item:
                out.append(item)
        return out

    data = _api_get("fixtures", params={"date": date_str, "timezone": TZ})
    resp = data.get("response") or []

    out: List[Dict[str, Any]] = []
    for it in resp[:MAX_FIXTURES]:
        fixture = it.get("fixture") or {}
        league = it.get("league") or {}
        teams = it.get("teams") or {}

        fixture_id = fixture.get("id")
        kickoff = fixture.get("date")
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")

        if not fixture_id or not home or not away:
            continue

        out.append(
            {
                "sport": "football",
                "fixture_id": int(fixture_id),
                "league_name": league.get("name") or "",
                "country_name": league.get("country") or "",
                "kickoff_local": kickoff or "",
                "home_team": home,
                "away_team": away,
                "odds": {},
                "standings": {},
                "injuries": [],
            }
        )
    return out


def _fetch_fixtures_expanding(slot: str, base_date: datetime.date) -> List[Dict[str, Any]]:
    """
    Bővülő keresés: alapból CSAK az adott nap.
    Ha valaki mégis engedélyezi (MAX_DAYS_AHEAD>0), akkor ma+1.. napon belül bővít.

    Profi fizetős csatornához ajánlott: MAX_DAYS_AHEAD=0.
    """
    slot = (slot or "DAY").upper()

    all_fx: List[Dict[str, Any]] = []
    for days_ahead in range(0, MAX_DAYS_AHEAD + 1):
        day = (base_date + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        chunk = _fetch_fixtures_for_date(day)
        all_fx.extend(chunk)

        slot_fx = _slot_filter(all_fx, slot)
        print(f"[matches] fixtures: date={day} added={len(chunk)} | slot={slot} now={len(slot_fx)} total={len(all_fx)}")

        if len(slot_fx) >= MIN_POOL:
            return all_fx

    return all_fx


def fetch_matches_for_today(slot: str = "DAY", date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Profi pool-logika (fizetős csatornára optimalizálva):
    - alapból CSAK az adott nap meccsei (MAX_DAYS_AHEAD=0)
    - először top/komoly felnőtt meccsek, aztán csak ha kell: egzotikus, youth, friendly
    - odds enrichment API-FOOTBALL odds endpointtal (csak API-Sports esetén), limitálva

    Paraméterek:
    - slot: DAY / EVENING
    - date: opcionális YYYY-MM-DD (backtest/recap/debug)
    """
    slot = (slot or "DAY").upper()

    base_date = datetime.date.today()
    if date:
        try:
            base_date = datetime.date.fromisoformat(str(date).strip())
        except Exception:
            base_date = datetime.date.today()

    fixtures = _fetch_fixtures_expanding(slot, base_date=base_date)
    print(f"[matches] fixtures expanded total -> {len(fixtures)}")

    slot_fixtures_all = _slot_filter(fixtures, slot)
    print(f"[matches] slot={slot} all -> {len(slot_fixtures_all)}")

    if not slot_fixtures_all:
        print(f"[matches] slot üres ({slot}), visszaadom a pool összes meccsét.")
        slot_fixtures_all = fixtures

    ranked = sorted(slot_fixtures_all, key=_rank_bucket)

    # építsünk minimum poolt, de csak amennyi kell
    slot_fixtures: List[Dict[str, Any]] = []
    for m in ranked:
        slot_fixtures.append(m)
        if len(slot_fixtures) >= MIN_POOL:
            break

    if len(slot_fixtures) < MIN_POOL and len(slot_fixtures_all) > len(slot_fixtures):
        slot_fixtures = ranked

    print(
        f"[matches] pool built: {len(slot_fixtures)} (target MIN_POOL={MIN_POOL}) | "
        f"top={sum(1 for m in slot_fixtures if _rank_bucket(m)==0)} "
        f"adult_exotic={sum(1 for m in slot_fixtures if _rank_bucket(m)==1)} "
        f"youth={sum(1 for m in slot_fixtures if _rank_bucket(m)==2)} "
        f"friendly={sum(1 for m in slot_fixtures if _rank_bucket(m)==3)}"
    )

    # Odds enrichment (API-Sports only)
    odds_ok = 0
    looked = 0
    for m in slot_fixtures:
        if looked >= ODDS_LOOKUP_LIMIT:
            break
        fid = int(m["fixture_id"])
        odds = fetch_api_football_1x2_odds(fid)
        looked += 1
        if odds and odds.get("1") and odds.get("X") and odds.get("2"):
            m["odds"] = odds
            m["odds_source"] = "api-sports"
            odds_ok += 1

    # If we are on SportsDataIO (no native odds), try The Odds API as a supplement
    try:
        if resolve_sports_provider() == "sportsdataio":
            _enrich_odds_from_theoddsapi(slot_fixtures)
    except Exception:
        pass

    print(f"[matches] odds enriched: {odds_ok}/{min(len(slot_fixtures), ODDS_LOOKUP_LIMIT)} (limit={ODDS_LOOKUP_LIMIT})")

    if slot_fixtures:
        print("[matches] RAW MATCH EXAMPLE:\n", slot_fixtures[0])

    # annotate each match with its quality bucket for downstream DB storage / analysis
    for m in slot_fixtures:
        try:
            m["bucket"] = _rank_bucket(m)
        except Exception:
            m["bucket"] = None

    return slot_fixtures
