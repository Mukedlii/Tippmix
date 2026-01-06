import os
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

API_FOOTBALL_KEY = (os.getenv("SPORTS_API_KEY") or "").strip()
TZ = os.getenv("TIPPMIX_TIMEZONE", "Europe/Budapest")

# Ha túl kevés meccs van az adott slotban, ennyi órával engedjük kitolni a keresést (0 = szigorúan ma)
# Te azt kéred: csak aznapi meccsek -> maradjon 0
FALLBACK_HOURS = int(os.getenv("TIPPMIX_FALLBACK_HOURS", "0"))

# mennyi meccset engedünk max feldolgozni (ha túl sok, lassul az odds lekérés)
MAX_FIXTURES = int(os.getenv("TIPPMIX_MAX_FIXTURES", "180"))


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _extract_hour(iso: str) -> Optional[int]:
    # pl: 2026-01-06T20:45:00+01:00
    if not iso or "T" not in iso:
        return None
    try:
        return int(iso.split("T")[1][:2])
    except Exception:
        return None


def _slot_filter(fixtures: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()
    out: List[Dict[str, Any]] = []
    for f in fixtures:
        h = _extract_hour(str(f.get("kickoff_local") or ""))
        if h is None:
            out.append(f)
            continue
        if slot == "DAY":
            if 9 <= h < 16:
                out.append(f)
        else:
            if 16 <= h <= 23:
                out.append(f)
    return out


def _api_get(path: str, params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    if not API_FOOTBALL_KEY:
        raise RuntimeError("SPORTS_API_KEY nincs beállítva")
    url = f"https://v3.football.api-sports.io/{path.lstrip('/')}"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"API error {r.status_code}: {r.text[:300]}")
    return r.json() or {}


def _fetch_today_fixtures() -> List[Dict[str, Any]]:
    today = datetime.date.today().strftime("%Y-%m-%d")

    # API-FOOTBALL fixtures (ma)
    data = _api_get("fixtures", params={"date": today, "timezone": TZ})
    resp = data.get("response") or []
    out: List[Dict[str, Any]] = []

    for it in resp[:MAX_FIXTURES]:
        fixture = it.get("fixture") or {}
        league = it.get("league") or {}
        teams = it.get("teams") or {}

        fixture_id = fixture.get("id")
        kickoff = fixture.get("date")  # timezone param miatt már a TZ-ben jön

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
                "odds": {},  # később töltjük
            }
        )

    return out


def _fetch_1x2_odds_api_football(fixture_id: int) -> Optional[Dict[str, float]]:
    """
    API-FOOTBALL odds endpoint.
    Free csomagnál lehet, hogy visszadob / üres.
    Ha van adat, visszaad {"1":..., "X":..., "2":...}
    """
    try:
        data = _api_get("odds", params={"fixture": fixture_id})
    except Exception as e:
        print(f"[odds] api-football odds hiba fixture={fixture_id}: {repr(e)}")
        return None

    resp = data.get("response") or []
    if not resp:
        return None

    # response szerkezete csomagfüggő, ezért védetten keresünk
    # Tipikusan: response[0]["bookmakers"][0]["bets"]... "values"
    best_1 = best_x = best_2 = None

    for row in resp:
        bookmakers = row.get("bookmakers") or []
        for bm in bookmakers:
            bets = bm.get("bets") or []
            for bet in bets:
                # keressük a 1X2 piacot (név alapján)
                bet_name = str(bet.get("name") or "").lower()
                if "match winner" not in bet_name and "1x2" not in bet_name and "fulltime result" not in bet_name:
                    continue
                values = bet.get("values") or []
                for v in values:
                    label = str(v.get("value") or "").strip().lower()
                    odd = _safe_float(v.get("odd"))
                    if not odd or odd <= 1.01:
                        continue
                    if label in ("home", "1"):
                        best_1 = odd if best_1 is None else max(best_1, odd)
                    elif label in ("draw", "x"):
                        best_x = odd if best_x is None else max(best_x, odd)
                    elif label in ("away", "2"):
                        best_2 = odd if best_2 is None else max(best_2, odd)

    out: Dict[str, float] = {}
    if best_1 is not None:
        out["1"] = best_1
    if best_x is not None:
        out["X"] = best_x
    if best_2 is not None:
        out["2"] = best_2

    return out if out else None


def fetch_matches_for_today(slot: str = "DAY") -> List[Dict[str, Any]]:
    """
    Fő belépési pont.
    - Ma lekéri a fixtures-t API-FOOTBALL-ból (timezone=Europe/Budapest)
    - Slot szűrés
    - Odds enrichment API-FOOTBALL odds endpointtal
    """
    slot = (slot or "DAY").upper()

    fixtures = _fetch_today_fixtures()
    print(f"[matches] api-football fixtures today -> {len(fixtures)}")

    slot_fixtures = _slot_filter(fixtures, slot)
    print(f"[matches] slot={slot} -> {len(slot_fixtures)}")

    # Ha a slot üres, de te mindig akarsz tippet: visszaadjuk a mai összeset
    # (te ezt már korábban is így csináltad)
    if not slot_fixtures:
        print(f"[matches] slot üres ({slot}), visszaadom a mai összes meccset.")
        slot_fixtures = fixtures

    # Odds enrichment
    odds_ok = 0
    for m in slot_fixtures:
        fid = int(m["fixture_id"])
        odds = _fetch_1x2_odds_api_football(fid)
        if odds:
            m["odds"] = odds
            odds_ok += 1

    print(f"[matches] odds enriched: {odds_ok}/{len(slot_fixtures)}")
    if slot_fixtures:
        print("[matches] RAW MATCH EXAMPLE:\n", slot_fixtures[0])

    return slot_fixtures
