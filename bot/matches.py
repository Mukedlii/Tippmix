import os
import re
import datetime
from typing import Any, Dict, List, Optional

import requests

from bot.odds import fetch_api_football_1x2_odds

API_FOOTBALL_KEY = (os.getenv("SPORTS_API_KEY") or "").strip()
TZ = os.getenv("TIPPMIX_TIMEZONE", "Europe/Budapest")

MAX_FIXTURES = int(os.getenv("TIPPMIX_MAX_FIXTURES", "200"))
ODDS_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_ODDS_LOOKUP_LIMIT", "120"))

TOP_LEAGUE_KEYWORDS = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "UEFA Champions League", "Champions League",
    "UEFA Europa League", "Europa League",
    "UEFA Europa Conference League", "Conference League",
    "Eredivisie", "Primeira Liga", "Scottish Premiership",
    "FA Cup", "Copa del Rey", "DFB Pokal", "Coppa Italia",
]

YOUTH_PATTERNS = [
    r"\bU\d{2}\b", r"\bU-?\d{2}\b", r"\bYouth\b", r"\bReserve\b", r"\bB Team\b"
]

FRIENDLY_PATTERNS = [r"friendly", r"barátságos"]


def _api_get(path: str, params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    if not API_FOOTBALL_KEY:
        raise RuntimeError("SPORTS_API_KEY nincs beállítva")
    url = f"https://v3.football.api-sports.io/{path.lstrip('/')}"
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
    txt = f"{match.get('league_name','')} {match.get('home_team','')} {match.get('away_team','')}".lower()
    for p in YOUTH_PATTERNS:
        if re.search(p, txt, flags=re.IGNORECASE):
            return True
    return False


def _is_friendly(match: Dict[str, Any]) -> bool:
    txt = f"{match.get('league_name','')}".lower()
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
    2 = youth
    3 = friendly / legalja
    """
    if _is_friendly(match):
        return 3
    if _is_top_match(match) and not _is_youth(match):
        return 0
    if not _is_youth(match):
        return 1
    return 2


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
                "odds": {},   # ide töltjük be később
                "standings": {},  # később bővíthető
                "injuries": [],   # később bővíthető
            }
        )

    return out


def fetch_matches_for_today(slot: str = "DAY") -> List[Dict[str, Any]]:
    """
    - csak aznapi meccsek (timezone=Europe/Budapest)
    - slot szűrés (DAY / EVENING)
    - EVENING-ben: top felnőtt -> felnőtt egzotikus -> youth -> friendly
    - odds enrichment API-FOOTBALL odds endpointtal (limitálva)
    """
    slot = (slot or "DAY").upper()

    fixtures = _fetch_today_fixtures()
    print(f"[matches] api-football fixtures today -> {len(fixtures)}")

    slot_fixtures = _slot_filter(fixtures, slot)
    print(f"[matches] slot={slot} -> {len(slot_fixtures)}")

    # Ha a slot üres (pl. nappal nincs 9-16 között), akkor is küldjünk tippeket:
    if not slot_fixtures:
        print(f"[matches] slot üres ({slot}), visszaadom a mai összes meccset.")
        slot_fixtures = fixtures

    # ESTE prioritás
    if slot == "EVENING":
        slot_fixtures = sorted(slot_fixtures, key=_priority_bucket_evening)
        print("[matches] EVENING priority: top -> adult -> youth -> friendly")

    # Odds enrichment (limitált)
    odds_ok = 0
    looked = 0
    for m in slot_fixtures:
        if looked >= ODDS_LOOKUP_LIMIT:
            break
        fid = int(m["fixture_id"])
        odds = fetch_api_football_1x2_odds(fid)
        looked += 1
        if odds:
            m["odds"] = odds
            odds_ok += 1

    print(f"[matches] odds enriched: {odds_ok}/{min(len(slot_fixtures), ODDS_LOOKUP_LIMIT)} (limit={ODDS_LOOKUP_LIMIT})")

    if slot_fixtures:
        print("[matches] RAW MATCH EXAMPLE:\n", slot_fixtures[0])

    return slot_fixtures
