import os
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests


SPORTMONKS_BASE = "https://api.sportmonks.com/v3/football"
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def _get_token() -> str:
    token = os.getenv("SPORTMONKS_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SPORTMONKS_API_TOKEN nincs beállítva (GitHub Secrets + workflow env).")
    return token


def _request_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Dict[str, Any]:
    token = _get_token()
    params = dict(params or {})
    # SportMonks: api_token query param (gyors, egyszerű)  [oai_citation:4‡docs.sportmonks.com](https://docs.sportmonks.com/v3/welcome/authentication?utm_source=chatgpt.com)
    params["api_token"] = token

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"SportMonks HTTP {r.status_code}: {r.text[:500]}")
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"SportMonks request failed: {repr(last_err)}")


def _iso_to_budapest(iso_str: str) -> str:
    # SportMonks többnyire ISO időt ad. Kezeljük mindkét formát.
    s = (iso_str or "").strip()
    if not s:
        return "Ismeretlen időpont"
    try:
        # Python 3.11: fromisoformat elfogad +00:00-t
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        dt_local = dt.astimezone(BUDAPEST_TZ)
        return dt_local.isoformat()
    except Exception:
        return s


def get_fixtures_for_date(date_yyyy_mm_dd: str) -> List[Dict[str, Any]]:
    """
    SportMonks: fixtures by date range endpoint:
    /fixtures/between/{start}/{end}   [oai_citation:5‡docs.sportmonks.com](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures/get-fixtures-by-date-range?utm_source=chatgpt.com)
    """
    url = f"{SPORTMONKS_BASE}/fixtures/between/{date_yyyy_mm_dd}/{date_yyyy_mm_dd}"
    # includes: participants + league (hogy legyen csapatnév / liga név)
    params = {
        "include": "participants;league",
        "per_page": 100,
    }
    data = _request_json(url, params=params)
    return data.get("data") or []


def get_prematch_odds_for_fixture(fixture_id: int) -> List[Dict[str, Any]]:
    """
    SportMonks pre-match odds by fixture id:
    /odds/pre-match/fixtures/{ID}  [oai_citation:6‡docs.sportmonks.com](https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/standard-odds-feed/pre-match-odds/get-odds-by-fixture-id?utm_source=chatgpt.com)
    """
    url = f"{SPORTMONKS_BASE}/odds/pre-match/fixtures/{fixture_id}"
    data = _request_json(url, params={"per_page": 200})
    return data.get("data") or []


def _norm(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


def extract_home_away_participants(fixture: Dict[str, Any]) -> Tuple[str, str]:
    """
    SportMonks fixture -> participants meta.location: home/away (tipikusan).
    Ha nem találjuk, fallback első 2 résztvevő.
    """
    participants = fixture.get("participants") or []
    home = None
    away = None
    for p in participants:
        meta = p.get("meta") or {}
        loc = (meta.get("location") or "").lower()
        name = p.get("name")
        if loc == "home":
            home = name
        elif loc == "away":
            away = name

    if not home or not away:
        # fallback: első kettő
        if len(participants) >= 2:
            home = home or participants[0].get("name")
            away = away or participants[1].get("name")

    return (home or "Hazai csapat", away or "Vendég csapat")


def extract_league_name_country(fixture: Dict[str, Any]) -> Tuple[str, str]:
    league = fixture.get("league") or {}
    league_name = league.get("name") or "Ismeretlen liga"
    # ország név sokszor include-ból jön, de nem mindig. üresen hagyható.
    country = league.get("country") or ""
    return str(league_name), str(country)


def extract_kickoff_local(fixture: Dict[str, Any]) -> str:
    # gyakori mező: starting_at
    iso = fixture.get("starting_at") or fixture.get("kickoff") or fixture.get("date") or ""
    return _iso_to_budapest(str(iso))


def extract_1x2_odds_from_sportmonks_odds(
    odds_items: List[Dict[str, Any]],
    home_team: str,
    away_team: str,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    SportMonks odds válasz formátuma eltérhet feed/csomag szerint.
    Mi “robosztusan” próbáljuk összeszedni a decimal odds értékeket:
      - home: name/label tartalmazza a hazai csapatot
      - away: name/label tartalmazza a vendéget
      - draw: name/label 'draw' vagy 'x'
    Több találat esetén mediánt veszünk.
    """
    home_key = _norm(home_team)
    away_key = _norm(away_team)

    home_vals: List[float] = []
    draw_vals: List[float] = []
    away_vals: List[float] = []

    for it in odds_items or []:
        name = str(it.get("name") or it.get("label") or it.get("market_description") or "")
        val = it.get("value")
        try:
            v = float(val)
        except Exception:
            continue

        n = _norm(name)

        # draw
        if "draw" in n or n == "x":
            draw_vals.append(v)
            continue

        # home/away team match by name
        if home_key and home_key in n:
            home_vals.append(v)
            continue
        if away_key and away_key in n:
            away_vals.append(v)
            continue

        # néha 1 / 2 / X jelölések
        if n in ("1", "home"):
            home_vals.append(v)
        elif n in ("2", "away"):
            away_vals.append(v)

    def median(xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        xs2 = sorted(xs)
        mid = len(xs2) // 2
        if len(xs2) % 2 == 1:
            return xs2[mid]
        return (xs2[mid - 1] + xs2[mid]) / 2.0

    return median(home_vals), median(draw_vals), median(away_vals)
