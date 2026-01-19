import os
import re
import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

from bot.odds import fetch_api_football_1x2_odds
from bot.providers import sportmonks as sportmonks_provider

API_FOOTBALL_KEY = (os.getenv("SPORTS_API_KEY") or "").strip()
TZ = os.getenv("TIPPMIX_TIMEZONE", "Europe/Budapest")
SPORTMONKS_TOKEN = (os.getenv("SPORTMONKS_API_TOKEN") or "").strip()

MAX_FIXTURES = int(os.getenv("TIPPMIX_MAX_FIXTURES", "200"))
ODDS_LOOKUP_LIMIT = int(os.getenv("TIPPMIX_ODDS_LOOKUP_LIMIT", "120"))

# minimumok (hogy matches.py is tudja, mennyi meccs kell minimum a poolhoz)
MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))

# mennyire terjesszük ki a keresést "ma + hány napra előre", ha kevés a meccs
MAX_DAYS_AHEAD = int(os.getenv("TIPPMIX_MAX_DAYS_AHEAD", "3"))

# mekkora legyen minimum a pool (slot után számolva)
# ha nincs beállítva, számoljuk: VIP+FREE+12 (hogy legyen miből válogatni)
MIN_POOL = int(os.getenv("TIPPMIX_MIN_POOL", str(MIN_VIP + MIN_FREE + 12)))

FIXTURE_PROVIDERS = [p.strip().lower() for p in os.getenv("TIPPMIX_FIXTURE_PROVIDERS", "api_sports").split(",") if p.strip()]

TOP_LEAGUE_KEYWORDS = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "UEFA Champions League", "Champions League",
    "UEFA Europa League", "Europa League",
    "UEFA Europa Conference League", "Conference League",
    "Eredivisie", "Primeira Liga", "Scottish Premiership",
    "FA Cup", "Copa del Rey", "DFB Pokal", "Coppa Italia",
]

YOUTH_PATTERNS = [
    r"\bU\d{2}\b", r"\bU-?\d{2}\b", r"\bYouth\b", r"\bReserve\b", r"\bB Team\b",
    r"\bPrimavera\b", r"\bU23\b", r"\bU21\b", r"\bU20\b", r"\bU19\b"
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


def _norm_team_name(name: str) -> str:
    return "".join(ch.lower() for ch in (name or "") if ch.isalnum() or ch.isspace()).strip()


def _fixture_key(match: Dict[str, Any]) -> Tuple[str, str, str]:
    kickoff = str(match.get("kickoff_local") or "")
    date = kickoff.split("T")[0] if "T" in kickoff else kickoff.split(" ")[0]
    home = _norm_team_name(str(match.get("home_team") or ""))
    away = _norm_team_name(str(match.get("away_team") or ""))
    return date, home, away


def _merge_fixtures(fixtures_by_provider: List[Tuple[str, List[Dict[str, Any]]]]) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    ordered: List[Dict[str, Any]] = []
    for provider, items in fixtures_by_provider:
        for match in items:
            key = _fixture_key(match)
            if key in merged:
                continue
            merged[key] = match
            match["provider"] = provider
            ordered.append(match)
    return ordered


def _fetch_api_sports_fixtures_for_date(date_str: str) -> List[Dict[str, Any]]:
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


def _fetch_api_sports_fixtures_expanding(slot: str) -> List[Dict[str, Any]]:
    """
    Bővülő keresés: ma, holnap, holnapután...
    addig, amíg slot-szűrés után megvan legalább MIN_POOL db meccs.
    """
    slot = (slot or "DAY").upper()
    base = datetime.date.today()

    all_fx: List[Dict[str, Any]] = []

    for days_ahead in range(0, MAX_DAYS_AHEAD + 1):
        day = (base + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        chunk = _fetch_api_sports_fixtures_for_date(day)
        all_fx.extend(chunk)

        slot_fx = _slot_filter(all_fx, slot)
        print(f"[matches] api-sports fixtures: date={day} added={len(chunk)} | slot={slot} now={len(slot_fx)} total={len(all_fx)}")

        if len(slot_fx) >= MIN_POOL:
            return all_fx

    return all_fx


def _parse_sportmonks_fixture(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fixture_id = int(raw.get("id"))
    except Exception:
        return None

    starting = str(raw.get("starting_at") or "")
    kickoff = ""
    if starting:
        try:
            dt = datetime.datetime.fromisoformat(starting.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            kickoff = dt.astimezone(ZoneInfo(TZ)).isoformat()
        except Exception:
            kickoff = starting

    league = raw.get("league") or {}
    league_name = league.get("name") or ""
    country = league.get("country") or ""

    participants = raw.get("participants") or []
    home = away = None
    for p in participants:
        meta = p.get("meta") or {}
        loc = (meta.get("location") or "").lower()
        if loc == "home":
            home = p.get("name")
        elif loc == "away":
            away = p.get("name")
    if not home or not away:
        if len(participants) >= 2:
            home = home or participants[0].get("name")
            away = away or participants[1].get("name")

    if not home or not away:
        return None

    return {
        "sport": "football",
        "fixture_id": fixture_id,
        "league_name": league_name or "",
        "country_name": country or "",
        "kickoff_local": kickoff or "",
        "home_team": home,
        "away_team": away,
        "odds": {},
        "standings": {},
        "injuries": [],
    }


def _fetch_sportmonks_fixtures_for_date(date_str: str) -> List[Dict[str, Any]]:
    if not SPORTMONKS_TOKEN:
        return []
    raw = sportmonks_provider.fixtures_between(date_str, date_str)
    out: List[Dict[str, Any]] = []
    for it in raw[:MAX_FIXTURES]:
        parsed = _parse_sportmonks_fixture(it)
        if parsed:
            out.append(parsed)
    return out


def _fetch_sportmonks_fixtures_expanding(slot: str) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()
    base = datetime.date.today()

    all_fx: List[Dict[str, Any]] = []

    for days_ahead in range(0, MAX_DAYS_AHEAD + 1):
        day = (base + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        chunk = _fetch_sportmonks_fixtures_for_date(day)
        all_fx.extend(chunk)

        slot_fx = _slot_filter(all_fx, slot)
        print(f"[matches] sportmonks fixtures: date={day} added={len(chunk)} | slot={slot} now={len(slot_fx)} total={len(all_fx)}")

        if len(slot_fx) >= MIN_POOL:
            return all_fx

    return all_fx


def _fetch_fixtures_expanding(slot: str) -> List[Dict[str, Any]]:
    providers: List[Tuple[str, List[Dict[str, Any]]]] = []
    for provider in FIXTURE_PROVIDERS:
        if provider == "api_sports":
            if not API_FOOTBALL_KEY:
                print("[matches] api-sports provider disabled (SPORTS_API_KEY missing).")
                continue
            providers.append((provider, _fetch_api_sports_fixtures_expanding(slot)))
        elif provider == "sportmonks":
            if not SPORTMONKS_TOKEN:
                print("[matches] sportmonks provider disabled (SPORTMONKS_API_TOKEN missing).")
                continue
            providers.append((provider, _fetch_sportmonks_fixtures_expanding(slot)))
        else:
            print(f"[matches] provider skipped: {provider}")

    if not providers:
        return []

    return _merge_fixtures(providers)


def _fetch_sportmonks_1x2_odds(match: Dict[str, Any]) -> Dict[str, float]:
    if not SPORTMONKS_TOKEN:
        return {}
    try:
        fid = int(match.get("fixture_id"))
    except Exception:
        return {}
    odds_items = sportmonks_provider.prematch_odds_fixture(fid)
    o1, ox, o2 = sportmonks_provider.extract_1x2(
        odds_items, str(match.get("home_team") or ""), str(match.get("away_team") or "")
    )
    if not (o1 and ox and o2):
        return {}
    return {"1": float(o1), "X": float(ox), "2": float(o2)}


def fetch_matches_for_today(slot: str = "DAY") -> List[Dict[str, Any]]:
    """
    - bővülő meccs-pool (ma -> max MAX_DAYS_AHEAD), hogy meglegyen a minimum tipp pool
    - slot szűrés (DAY / EVENING)
    - EVENING-ben: top felnőtt -> felnőtt egzotikus -> youth -> friendly
    - odds enrichment provider-specifikus odds endpointtal (limitálva)
    """
    slot = (slot or "DAY").upper()

    # ✅ EZ A LÉNYEG: nem csak "ma", hanem bővülő keresés, hogy legyen elég meccs
    fixtures = _fetch_fixtures_expanding(slot)
    print(f"[matches] fixtures expanded total -> {len(fixtures)}")

    slot_fixtures = _slot_filter(fixtures, slot)
    print(f"[matches] slot={slot} -> {len(slot_fixtures)}")

    # ha valamiért a slot üres, akkor is visszaadjuk a teljes poolt (mert tipp mindig kell)
    if not slot_fixtures:
        print(f"[matches] slot üres ({slot}), visszaadom a pool összes meccsét.")
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
        provider = (m.get("provider") or "api_sports").lower()
        odds: Dict[str, float] = {}
        if provider == "api_sports":
            fid = int(m["fixture_id"])
            odds = fetch_api_football_1x2_odds(fid)
        elif provider == "sportmonks":
            odds = _fetch_sportmonks_1x2_odds(m)
        looked += 1
        if odds and odds.get("1") and odds.get("X") and odds.get("2"):
            m["odds"] = odds
            odds_ok += 1

    print(f"[matches] odds enriched: {odds_ok}/{min(len(slot_fixtures), ODDS_LOOKUP_LIMIT)} (limit={ODDS_LOOKUP_LIMIT})")

    if slot_fixtures:
        print("[matches] RAW MATCH EXAMPLE:\n", slot_fixtures[0])

    return slot_fixtures
