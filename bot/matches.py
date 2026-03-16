import os
import re
import datetime
from typing import Any, Dict, List, Optional

import requests

from bot.api_keys import get_api_sports_key, resolve_sports_provider
from bot.odds import fetch_api_football_1x2_odds
from bot.providers import sportsdataio
from bot.providers import sportmonks
from bot.providers import theoddsapi
from bot.providers import allsportsapi

TZ = os.getenv("TIPPMIX_TIMEZONE", "Europe/Budapest")

BLOCK_COUNTRIES = [x.strip().lower() for x in (os.getenv("TIPPMIX_BLOCK_COUNTRIES") or "").split(",") if x.strip()]
BLOCK_LEAGUES = [x.strip().lower() for x in (os.getenv("TIPPMIX_BLOCK_LEAGUES") or "").split(",") if x.strip()]

MAX_FIXTURES = int(os.getenv("TIPPMIX_MAX_FIXTURES", "200"))
ODDS_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_ODDS_LOOKUP_LIMIT", "120"))

MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    raw = str(raw).strip()
    if raw == "":
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


MAX_DAYS_AHEAD = _get_int_env("TIPPMIX_MAX_DAYS_AHEAD", 0)
MIN_POOL = int(os.getenv("TIPPMIX_MIN_POOL", str(MIN_VIP + MIN_FREE + 12)))

ALLOW_YOUTH = (os.getenv("TIPPMIX_ALLOW_YOUTH") or "").strip() == "1"
ALLOW_FRIENDLY = (os.getenv("TIPPMIX_ALLOW_FRIENDLY") or "").strip() == "1"

TOP_LEAGUE_KEYWORDS = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "UEFA Champions League", "Champions League",
    "UEFA Europa League", "Europa League",
    "UEFA Europa Conference League", "Conference League",
    "Eredivisie", "Primeira Liga", "Scottish Premiership",
    "FA Cup", "Copa del Rey", "DFB Pokal", "Coppa Italia",
]

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

FRIENDLY_PATTERNS = [r"friendly", r"friendlies", r"barátságos"]

# ─────────────────────────────────────────────
# football-data.org FREE provider
# Regisztrálj itt: https://www.football-data.org/client/register
# Ingyenes tier: 10 req/perc, top 12 liga, nincs bankkártya
# GitHub Actions Variable: SPORTS_DATA_PROVIDER=footballdata
#                          FOOTBALLDATA_API_KEY=<token>
# ─────────────────────────────────────────────

# Liga ID-k a football-data.org rendszerben (ingyenes tier)
FOOTBALLDATA_COMPETITION_IDS = [
    2021,  # Premier League
    2014,  # La Liga
    2002,  # Bundesliga
    2019,  # Serie A
    2015,  # Ligue 1
    2001,  # Champions League
    2018,  # Europa League
    2003,  # Eredivisie
    2017,  # Primeira Liga
    2016,  # Championship
]


def _footballdata_fetch_matches(date_str: str) -> List[Dict[str, Any]]:
    """Lekéri a napi meccseket a football-data.org ingyenes API-jából.

    Env:
      FOOTBALLDATA_API_KEY  – regisztrálás után kapott token (kötelező)
      FOOTBALLDATA_COMP_IDS – opcionális felülírás, pl. "2021,2014,2002"
    """
    api_key = (os.getenv("FOOTBALLDATA_API_KEY") or "").strip()
    if not api_key:
        print("[footballdata] FOOTBALLDATA_API_KEY nincs beállítva! Regisztrálj: https://www.football-data.org/client/register")
        return []

    # opcionális liga-felülírás env-ből
    env_ids = (os.getenv("FOOTBALLDATA_COMP_IDS") or "").strip()
    if env_ids:
        try:
            comp_ids = [int(x.strip()) for x in env_ids.split(",") if x.strip()]
        except Exception:
            comp_ids = FOOTBALLDATA_COMPETITION_IDS
    else:
        comp_ids = FOOTBALLDATA_COMPETITION_IDS

    headers = {"X-Auth-Token": api_key}
    out: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for comp_id in comp_ids:
        url = f"https://api.football-data.org/v4/competitions/{comp_id}/matches"
        params = {"dateFrom": date_str, "dateTo": date_str}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)
        except Exception as e:
            print(f"[footballdata] request hiba (comp={comp_id}): {repr(e)}")
            continue

        if resp.status_code == 429:
            print(f"[footballdata] rate limit (comp={comp_id}) – várj 60 mp-et vagy csökkentsd a ligák számát")
            continue

        if resp.status_code == 403:
            print(f"[footballdata] 403 – ez a liga nem érhető el az ingyenes tieren (comp={comp_id})")
            continue

        if resp.status_code != 200:
            print(f"[footballdata] HTTP {resp.status_code} (comp={comp_id}): {resp.text[:200]}")
            continue

        try:
            data = resp.json()
        except Exception as e:
            print(f"[footballdata] JSON parse hiba (comp={comp_id}): {repr(e)}")
            continue

        competition = data.get("competition") or {}
        comp_name = competition.get("name") or ""
        area = competition.get("area") or {}
        country_name = area.get("name") or ""

        for match in (data.get("matches") or []):
            fid = match.get("id")
            if not fid or fid in seen_ids:
                continue
            seen_ids.add(fid)

            home_team = (match.get("homeTeam") or {}).get("shortName") or (match.get("homeTeam") or {}).get("name") or ""
            away_team = (match.get("awayTeam") or {}).get("shortName") or (match.get("awayTeam") or {}).get("name") or ""

            if not home_team or not away_team:
                continue

            # státusz szűrés – csak tervezett meccsek
            status = (match.get("status") or "").upper()
            if status not in ("TIMED", "SCHEDULED", ""):
                continue

            kickoff = match.get("utcDate") or ""

            # odds: football-data.org ingyenes tierje NEM ad oddsot
            # The Odds API-val lehet enrichelni (ODDS_API_KEY env-vel)
            odds: Dict[str, Any] = {}

            # ha van odds a válaszban (paid tier), használjuk
            raw_odds = match.get("odds") or {}
            if raw_odds:
                try:
                    home_win = raw_odds.get("homeWin")
                    draw = raw_odds.get("draw")
                    away_win = raw_odds.get("awayWin")
                    if home_win and draw and away_win:
                        odds = {
                            "1": float(home_win),
                            "X": float(draw),
                            "2": float(away_win),
                        }
                except Exception:
                    pass

            out.append({
                "sport": "football",
                "fixture_id": int(fid),
                "league_name": comp_name,
                "country_name": country_name,
                "kickoff_local": kickoff,
                "home_team": home_team,
                "away_team": away_team,
                "odds": odds,
                "standings": {},
                "injuries": [],
            })

        # rate limit kímélet: 10 req/perc ingyenes tieren
        import time
        time.sleep(6)

    print(f"[footballdata] összesen {len(out)} meccs {date_str}-re")
    return out


# ─────────────────────────────────────────────
# Meglévő helper függvények (változatlan)
# ─────────────────────────────────────────────

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
    day_start = int(os.getenv("TIPPMIX_DAY_START_HOUR", "9"))
    day_end_excl = int(os.getenv("TIPPMIX_DAY_END_HOUR_EXCL", "19"))
    eve_start = int(os.getenv("TIPPMIX_EVENING_START_HOUR", str(day_end_excl)))
    eve_end_incl = int(os.getenv("TIPPMIX_EVENING_END_HOUR_INCL", "23"))

    out: List[Dict[str, Any]] = []
    for m in matches:
        h = _extract_hour(str(m.get("kickoff_local") or ""))
        if h is None:
            out.append(m)
            continue
        if slot == "DAY":
            if day_start <= h < day_end_excl:
                out.append(m)
        else:
            if eve_start <= h <= eve_end_incl:
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


def _is_blocked(match: Dict[str, Any]) -> bool:
    if not BLOCK_COUNTRIES and not BLOCK_LEAGUES:
        return False
    country = (match.get("country_name") or match.get("country") or "").lower()
    league = (match.get("league_name") or match.get("league") or "").lower()
    for bc in BLOCK_COUNTRIES:
        if bc and bc in country:
            return True
    for bl in BLOCK_LEAGUES:
        if bl and bl in league:
            return True
    return False


def _rank_bucket(match: Dict[str, Any]) -> int:
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
        return [k.strip() for k in env.split(",") if k.strip()]
    keys: List[str] = []
    for m in matches:
        league = (m.get("league_name") or "").lower()
        for k, sk in LEAGUE_TO_THEODDS_KEY.items():
            if k in league and sk not in keys:
                keys.append(sk)
    return keys


def _enrich_odds_from_theoddsapi(matches: List[Dict[str, Any]]) -> None:
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
    sport_keys = sport_keys[: max(0, max_req)]

    for sk in sport_keys:
        try:
            theoddsapi.fetch_odds_for_sport_key(sk)
        except Exception:
            continue

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


# ─────────────────────────────────────────────
# Fő fixture lekérő (provider switch)
# ─────────────────────────────────────────────

def _fetch_fixtures_for_date(date_str: str) -> List[Dict[str, Any]]:
    provider = resolve_sports_provider()

    # ── ÚJ: football-data.org ingyenes provider ──
    if provider == "footballdata":
        return _footballdata_fetch_matches(date_str)

    # ── ÚJ: teljesen ingyenes scraper provider (SofaScore/LiveScore/Flashscore) ──
    if provider == "free_scraper":
        from bot.providers.free_fixtures import fetch_free_fixtures
        return fetch_free_fixtures(date_str, top_leagues_only=True)

    if provider == "sportsdataio":
        games = sportsdataio.fetch_games_by_date(date_str)
        out: List[Dict[str, Any]] = []
        for game in games[:MAX_FIXTURES]:
            item = sportsdataio.normalize_game(game)
            if item:
                out.append(item)
        return out

    if provider == "sportmonks":
        fx = sportmonks.fixtures_between(date_str, date_str)
        out: List[Dict[str, Any]] = []
        for raw in fx[:MAX_FIXTURES]:
            try:
                fid = int(raw.get("id"))
            except Exception:
                continue
            parts = raw.get("participants") or []
            home = away = None
            for p in parts:
                meta = p.get("meta") or {}
                loc = (meta.get("location") or "").lower()
                if loc == "home":
                    home = p.get("name")
                elif loc == "away":
                    away = p.get("name")
            if (not home or not away) and len(parts) >= 2:
                home = home or parts[0].get("name")
                away = away or parts[1].get("name")
            league = raw.get("league") or {}
            league_name = league.get("name") or ""
            country_name = league.get("country") or ""
            kickoff = raw.get("starting_at") or ""
            if not home or not away:
                continue
            out.append({
                "sport": "football",
                "fixture_id": fid,
                "league_name": league_name,
                "country_name": country_name,
                "kickoff_local": str(kickoff),
                "home_team": home,
                "away_team": away,
                "odds": {},
                "standings": {},
                "injuries": [],
            })
        return out

    if provider == "allsportsapi":
        fx = allsportsapi.fixtures_between(date_str, date_str)
        out: List[Dict[str, Any]] = []
        for raw in fx[:MAX_FIXTURES]:
            try:
                fid = int(raw.get("event_key"))
            except Exception:
                continue
            home = raw.get("event_home_team")
            away = raw.get("event_away_team")
            league_name = raw.get("league_name") or ""
            country_name = raw.get("country_name") or ""
            ko = (raw.get("event_date") or "") + "T" + (raw.get("event_time") or "")
            if not home or not away:
                continue
            out.append({
                "sport": "football",
                "fixture_id": fid,
                "league_name": str(league_name),
                "country_name": str(country_name),
                "kickoff_local": str(ko),
                "home_team": str(home),
                "away_team": str(away),
                "odds": {},
                "standings": {},
                "injuries": [],
            })
        return out

    # default: api-sports (fizetős)
    data = _api_get("fixtures", params={"date": date_str, "timezone": TZ})
    resp = data.get("response") or []
    out: List[Dict[str, Any]] = []
    for it in resp[:MAX_FIXTURES]:
        fixture = it.get("fixture") or {}
        league = it.get("league") or {}
        teams = it.get("teams") or {}
        fixture_id = fixture.get("id")
        kickoff = fixture.get("date")

        home_obj = teams.get("home") or {}
        away_obj = teams.get("away") or {}
        home = home_obj.get("name")
        away = away_obj.get("name")
        home_id = home_obj.get("id")
        away_id = away_obj.get("id")

        league_id = league.get("id")
        season = league.get("season")

        if not fixture_id or not home or not away:
            continue

        out.append({
            "sport": "football",
            "fixture_id": int(fixture_id),
            "league_id": int(league_id) if league_id is not None else None,
            "season": int(season) if season is not None else None,
            "league_name": league.get("name") or "",
            "country_name": league.get("country") or "",
            "kickoff_local": kickoff or "",
            "home_team_id": int(home_id) if home_id is not None else None,
            "away_team_id": int(away_id) if away_id is not None else None,
            "home_team": home,
            "away_team": away,
            "odds": {},
            "standings": {},
            "injuries": [],
        })
    return out


def _fetch_fixtures_expanding(slot: str, base_date: datetime.date) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()

    def enough(fixtures: List[Dict[str, Any]]) -> bool:
        slot_fx = _slot_filter(fixtures, slot)
        tmp = slot_fx
        if BLOCK_COUNTRIES or BLOCK_LEAGUES:
            tmp = [m for m in tmp if not _is_blocked(m)]
        if not ALLOW_YOUTH:
            tmp = [m for m in tmp if not _is_youth(m)]
        if not ALLOW_FRIENDLY:
            tmp = [m for m in tmp if not _is_friendly(m)]
        return len(tmp) >= MIN_POOL

    all_fx: List[Dict[str, Any]] = []
    max_ahead = max(0, MAX_DAYS_AHEAD)

    for days_ahead in range(0, max_ahead + 1):
        day = (base_date + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        chunk = _fetch_fixtures_for_date(day)
        all_fx.extend(chunk)
        slot_fx = _slot_filter(all_fx, slot)
        print(f"[matches] fixtures: date={day} added={len(chunk)} | slot={slot} now={len(slot_fx)} total={len(all_fx)}")
        if enough(all_fx):
            return all_fx

    hard_cap = 2
    if max_ahead < hard_cap:
        for days_ahead in range(max_ahead + 1, hard_cap + 1):
            day = (base_date + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            chunk = _fetch_fixtures_for_date(day)
            all_fx.extend(chunk)
            slot_fx = _slot_filter(all_fx, slot)
            print(f"[matches] expand fallback: date={day} added={len(chunk)} | slot={slot} now={len(slot_fx)} total={len(all_fx)}")
            if enough(all_fx):
                return all_fx

    return all_fx


def fetch_matches_for_today(slot: str = "DAY", date: Optional[str] = None) -> List[Dict[str, Any]]:
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

    if BLOCK_COUNTRIES or BLOCK_LEAGUES:
        before = len(slot_fixtures_all)
        slot_fixtures_all = [m for m in slot_fixtures_all if not _is_blocked(m)]
        after = len(slot_fixtures_all)
        if before != after:
            print(f"[matches] blacklist filtered: {before}->{after}")

    if not ALLOW_YOUTH:
        before = len(slot_fixtures_all)
        slot_fixtures_all = [m for m in slot_fixtures_all if not _is_youth(m)]
        after = len(slot_fixtures_all)
        if before != after:
            print(f"[matches] youth filtered: {before}->{after}")

    if not ALLOW_FRIENDLY:
        before = len(slot_fixtures_all)
        slot_fixtures_all = [m for m in slot_fixtures_all if not _is_friendly(m)]
        after = len(slot_fixtures_all)
        if before != after:
            print(f"[matches] friendly filtered: {before}->{after}")

    ranked = sorted(slot_fixtures_all, key=_rank_bucket)

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

    odds_ok_full = 0
    looked = 0
    provider = resolve_sports_provider()

    if provider == "api-sports":
        try:
            target_full_odds = int(os.getenv("TIPPMIX_TARGET_FULL_ODDS", "14"))
        except Exception:
            target_full_odds = 14

        for m in slot_fixtures:
            if looked >= ODDS_LOOKUP_LIMIT:
                break
            if odds_ok_full >= target_full_odds:
                break
            fid = int(m["fixture_id"])
            odds = fetch_api_football_1x2_odds(fid)
            looked += 1
            if odds and (odds.get("1") or odds.get("X") or odds.get("2")):
                m["odds"] = odds
                m["odds_source"] = "api-sports"
                if odds.get("1") and odds.get("X") and odds.get("2"):
                    odds_ok_full += 1

    elif provider == "sportmonks":
        for m in slot_fixtures:
            if looked >= ODDS_LOOKUP_LIMIT:
                break
            fid = int(m["fixture_id"])
            try:
                items = sportmonks.prematch_odds_fixture(fid)
                o1, ox, o2 = sportmonks.extract_1x2(items, m.get("home_team") or "", m.get("away_team") or "")
                looked += 1
                if o1 and ox and o2:
                    m["odds"] = {"1": float(o1), "X": float(ox), "2": float(o2)}
                    m["odds_source"] = "sportmonks"
                    odds_ok_full += 1
            except Exception:
                looked += 1
                continue

    # The Odds API supplement (football-data.org esetén különösen hasznos, mert az nincs odds)
    try:
        _enrich_odds_from_theoddsapi(slot_fixtures)
    except Exception:
        pass

    print(
        f"[matches] odds enriched (full 1X2): {odds_ok_full}/{min(len(slot_fixtures), ODDS_LOOKUP_LIMIT)} "
        f"(limit={ODDS_LOOKUP_LIMIT})"
    )

    if slot_fixtures:
        print("[matches] RAW MATCH EXAMPLE:\n", slot_fixtures[0])

    for m in slot_fixtures:
        try:
            m["bucket"] = _rank_bucket(m)
        except Exception:
            m["bucket"] = None

    return slot_fixtures








