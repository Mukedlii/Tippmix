import os
import re
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from bot.odds import fetch_api_football_1x2_odds

API_FOOTBALL_KEY = (os.getenv("SPORTS_API_KEY") or "").strip()
TZ = os.getenv("TIPPMIX_TIMEZONE", "Europe/Budapest")

MAX_FIXTURES = int(os.getenv("TIPPMIX_MAX_FIXTURES", "220"))

ODDS_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_ODDS_LOOKUP_LIMIT", "120"))
STANDINGS_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_STANDINGS_LOOKUP_LIMIT", "40"))  # ligánként cache
LAST5_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_LAST5_LOOKUP_LIMIT", "80"))          # csapatonként cache
INJURY_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_INJURY_LOOKUP_LIMIT", "80"))        # fixture-önként

TOP_LEAGUE_KEYWORDS = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "UEFA Champions League", "Champions League",
    "UEFA Europa League", "Europa League",
    "UEFA Europa Conference League", "Conference League",
    "Eredivisie", "Primeira Liga", "Scottish Premiership",
    "FA Cup", "Copa del Rey", "DFB Pokal", "Coppa Italia",
]

YOUTH_PATTERNS = [
    r"\bU\d{2}\b", r"\bU-?\d{2}\b", r"\bYouth\b", r"\bReserve\b", r"\bB Team\b", r"\bPrimavera\b"
]
FRIENDLY_PATTERNS = [r"friendly", r"barátságos"]

_API_BASE = "https://v3.football.api-sports.io"

# futás-cache-ek (rate-limit ellen)
_STANDINGS_CACHE: Dict[Tuple[int, int], Dict[int, Dict[str, Any]]] = {}  # (league_id, season) -> team_id -> row
_LAST5_CACHE: Dict[Tuple[int, int, int], Dict[str, Any]] = {}           # (team_id, league_id, season) -> summary
_INJ_CACHE: Dict[int, List[str]] = {}                                   # fixture_id -> injuries list


def _api_get(path: str, params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    if not API_FOOTBALL_KEY:
        raise RuntimeError("SPORTS_API_KEY nincs beállítva")
    url = f"{_API_BASE}/{path.lstrip('/')}"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
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


def _priority_bucket_evening(match: Dict[str, Any]) -> int:
    """
    0 = top / komoly felnőtt
    1 = felnőtt (nem top), nem youth, nem friendly
    2 = egzotikus/alsóbb felnőtt
    3 = youth
    4 = friendly
    """
    if _is_friendly(match):
        return 4
    if _is_top_match(match) and not _is_youth(match):
        return 0
    if (not _is_youth(match)) and (match.get("country_name") in ("England", "Spain", "Germany", "Italy", "France", "Netherlands", "Portugal", "Scotland")):
        return 1
    if not _is_youth(match):
        return 2
    return 3


def _fetch_today_fixtures() -> List[Dict[str, Any]]:
    today = datetime.date.today().strftime("%Y-%m-%d")
    data = _api_get("fixtures", params={"date": today, "timezone": TZ})
    resp = data.get("response") or []

    out: List[Dict[str, Any]] = []
    for it in resp[:MAX_FIXTURES]:
        fixture = it.get("fixture") or {}
        league = it.get("league") or {}
        teams = it.get("teams") or {}

        fixture_id = fixture.get("id")
        kickoff = fixture.get("date")

        league_id = league.get("id")
        season = league.get("season")
        league_name = league.get("name") or ""
        country = league.get("country") or ""

        home = teams.get("home") or {}
        away = teams.get("away") or {}
        home_id = home.get("id")
        away_id = away.get("id")
        home_name = home.get("name")
        away_name = away.get("name")

        if not fixture_id or not home_name or not away_name:
            continue

        out.append(
            {
                "sport": "football",
                "fixture_id": int(fixture_id),
                "league_id": int(league_id) if league_id else None,
                "season": int(season) if season else None,
                "league_name": league_name,
                "country_name": country,
                "kickoff_local": kickoff or "",

                "home_team_id": int(home_id) if home_id else None,
                "away_team_id": int(away_id) if away_id else None,
                "home_team": home_name,
                "away_team": away_name,

                # enrichment
                "odds": {},
                "standings": {},
                "injuries": [],
                "form": {},  # home_last5 / away_last5
            }
        )

    return out


def _fetch_standings_map(league_id: int, season: int) -> Dict[int, Dict[str, Any]]:
    key = (int(league_id), int(season))
    if key in _STANDINGS_CACHE:
        return _STANDINGS_CACHE[key]

    try:
        data = _api_get("standings", params={"league": league_id, "season": season})
        resp = data.get("response") or []
        if not resp:
            _STANDINGS_CACHE[key] = {}
            return {}

        league_obj = (resp[0].get("league") or {})
        groups = league_obj.get("standings") or []
        if not groups:
            _STANDINGS_CACHE[key] = {}
            return {}

        table = groups[0] or []
        out: Dict[int, Dict[str, Any]] = {}

        for row in table:
            team = row.get("team") or {}
            tid = team.get("id")
            if not tid:
                continue
            all_ = row.get("all") or {}
            goals = all_.get("goals") or {}
            out[int(tid)] = {
                "rank": row.get("rank"),
                "points": row.get("points"),
                "goalsDiff": row.get("goalsDiff"),
                "form": row.get("form"),
                "played": all_.get("played"),
                "gf": goals.get("for"),
                "ga": goals.get("against"),
            }

        _STANDINGS_CACHE[key] = out
        return out

    except Exception:
        _STANDINGS_CACHE[key] = {}
        return {}


def _summarize_last5(team_id: int, league_id: int, season: int) -> Dict[str, Any]:
    key = (int(team_id), int(league_id), int(season))
    if key in _LAST5_CACHE:
        return _LAST5_CACHE[key]

    try:
        data = _api_get("fixtures", params={
            "team": team_id,
            "league": league_id,
            "season": season,
            "last": 5,
            "status": "FT",
            "timezone": TZ,
        })
        resp = data.get("response") or []
        if not resp:
            _LAST5_CACHE[key] = {}
            return {}

        w = d = l = gf = ga = pts = 0
        seq: List[str] = []

        for it in resp[:5]:
            teams = it.get("teams") or {}
            goals = it.get("goals") or {}
            home = teams.get("home") or {}
            away = teams.get("away") or {}
            hg = goals.get("home")
            ag = goals.get("away")
            if hg is None or ag is None:
                continue

            is_home = int(home.get("id") or 0) == int(team_id)
            my = hg if is_home else ag
            opp = ag if is_home else hg
            gf += my
            ga += opp

            if my > opp:
                w += 1; pts += 3; seq.append("W")
            elif my == opp:
                d += 1; pts += 1; seq.append("D")
            else:
                l += 1; seq.append("L")

        out = {"wdl": "-".join(seq), "points": pts, "gf": gf, "ga": ga, "w": w, "d": d, "l": l}
        _LAST5_CACHE[key] = out
        return out

    except Exception:
        _LAST5_CACHE[key] = {}
        return {}


def _fetch_injuries_for_fixture(fixture_id: int) -> List[str]:
    if fixture_id in _INJ_CACHE:
        return _INJ_CACHE[fixture_id]

    try:
        data = _api_get("injuries", params={"fixture": fixture_id})
        resp = data.get("response") or []
        out: List[str] = []
        for it in resp[:12]:
            player = (it.get("player") or {}).get("name") or ""
            reason = it.get("reason") or ""
            if player:
                out.append(f"{player} – {reason}".strip(" –"))
        _INJ_CACHE[fixture_id] = out
        return out
    except Exception:
        _INJ_CACHE[fixture_id] = []
        return []


def fetch_matches_for_today(slot: str = "DAY") -> List[Dict[str, Any]]:
    """
    - csak aznapi meccsek (timezone=Europe/Budapest)
    - slot szűrés (DAY / EVENING)
    - EVENING-ben: top felnőtt -> felnőtt -> egzotikus -> youth -> friendly
    - enrichment: odds + standings + last5 + injuries (free plan kompatibilis, hibát lenyel)
    """
    slot = (slot or "DAY").upper()

    fixtures = _fetch_today_fixtures()
    print(f"[matches] api-football fixtures today -> {len(fixtures)}")

    slot_fixtures = _slot_filter(fixtures, slot)
    print(f"[matches] slot={slot} -> {len(slot_fixtures)}")

    if not slot_fixtures:
        print(f"[matches] slot üres ({slot}), visszaadom a mai összes meccset.")
        slot_fixtures = fixtures

    if slot == "EVENING":
        slot_fixtures = sorted(slot_fixtures, key=_priority_bucket_evening)
        print("[matches] EVENING priority: top -> adult -> exotic -> youth -> friendly")

    # --- ODDS enrichment (limit)
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
            odds_ok += 1
    print(f"[matches] odds enriched: {odds_ok}/{min(len(slot_fixtures), ODDS_LOOKUP_LIMIT)} (limit={ODDS_LOOKUP_LIMIT})")

    # --- STANDINGS + LAST5 + INJURIES enrichment (limitálva / cache)
    standings_done = 0
    last5_done = 0
    inj_done = 0

    for m in slot_fixtures:
        league_id = m.get("league_id")
        season = m.get("season")
        home_id = m.get("home_team_id")
        away_id = m.get("away_team_id")
        fixture_id = m.get("fixture_id")

        # standings (ligánként cache-elve)
        if standings_done < STANDINGS_LOOKUP_LIMIT and league_id and season and home_id and away_id:
            st_map = _fetch_standings_map(int(league_id), int(season))
            standings_done += 1
            if st_map:
                m["standings"] = {
                    "home": st_map.get(int(home_id), {}),
                    "away": st_map.get(int(away_id), {}),
                }

        # last5 (csapatonként cache-elve)
        if last5_done < LAST5_LOOKUP_LIMIT and league_id and season:
            if home_id:
                m["form"]["home_last5"] = _summarize_last5(int(home_id), int(league_id), int(season))
                last5_done += 1
            if away_id and last5_done < LAST5_LOOKUP_LIMIT:
                m["form"]["away_last5"] = _summarize_last5(int(away_id), int(league_id), int(season))
                last5_done += 1

        # injuries
        if inj_done < INJURY_LOOKUP_LIMIT and fixture_id:
            inj = _fetch_injuries_for_fixture(int(fixture_id))
            inj_done += 1
            if inj:
                m["injuries"] = inj

    if slot_fixtures:
        print("[matches] RAW MATCH EXAMPLE:\n", slot_fixtures[0])

    return slot_fixtures
