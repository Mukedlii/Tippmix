import os
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from bot.api_keys import get_api_sports_key

BASE_URL = os.getenv("SPORTS_API_BASE_URL", "https://v3.football.api-sports.io").rstrip("/")
TIMEZONE = os.getenv("SPORTS_API_TIMEZONE", "Europe/Budapest")


def _get(path: str, params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    headers = {
        "x-apisports-key": get_api_sports_key(),
    }
    url = f"{BASE_URL}{path}"

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"API-Sports HTTP {r.status_code}: {r.text[:600]}")
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"API-Sports request failed: {repr(last_err)}")


def fetch_fixtures(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """
    date_from/date_to: YYYY-MM-DD
    """
    data = _get("/fixtures", {"from": date_from, "to": date_to, "timezone": TIMEZONE})
    return data.get("response") or []


def _norm_name(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


def parse_fixture(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fx = raw.get("fixture") or {}
        lg = raw.get("league") or {}
        teams = raw.get("teams") or {}

        fixture_id = int(fx.get("id"))
        kickoff = fx.get("date")  # ISO, timezone param miatt helyi
        league_id = int(lg.get("id")) if lg.get("id") is not None else None
        season = int(lg.get("season")) if lg.get("season") is not None else None
        league_name = lg.get("name") or "Ismeretlen liga"
        country = lg.get("country") or ""

        home = teams.get("home") or {}
        away = teams.get("away") or {}
        home_id = int(home.get("id")) if home.get("id") is not None else None
        away_id = int(away.get("id")) if away.get("id") is not None else None
        home_name = home.get("name") or "Hazai"
        away_name = away.get("name") or "Vendég"

        return {
            "fixture_id": fixture_id,
            "kickoff_local": str(kickoff),
            "league_id": league_id,
            "season": season,
            "league_name": str(league_name),
            "country_name": str(country),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "home_team": str(home_name),
            "away_team": str(away_name),

            # extra helyek
            "standings": None,
            "form": None,
            "injuries": None,
            "odds": {"1": None, "X": None, "2": None},
        }
    except Exception:
        return None


def fetch_injuries_by_fixture(fixture_id: int) -> List[Dict[str, Any]]:
    data = _get("/injuries", {"fixture": fixture_id, "timezone": TIMEZONE})
    resp = data.get("response") or []
    out: List[Dict[str, Any]] = []
    for it in resp:
        player = (it.get("player") or {}).get("name") or ""
        team = (it.get("team") or {}).get("name") or ""
        reason = it.get("reason") or ""
        out.append({"player": player, "team": team, "reason": reason})
    return out


def fetch_standings(league_id: int, season: int) -> Dict[int, Dict[str, Any]]:
    """
    Visszaad: team_id -> {rank, points, goalsDiff, form}
    """
    data = _get("/standings", {"league": league_id, "season": season})
    resp = data.get("response") or []
    if not resp:
        return {}

    # szerkezet általában: response[0].league.standings[0] -> lista
    league = (resp[0] or {}).get("league") or {}
    standings = league.get("standings") or []
    table = standings[0] if standings else []
    out: Dict[int, Dict[str, Any]] = {}
    for row in table:
        team = row.get("team") or {}
        tid = team.get("id")
        if tid is None:
            continue
        try:
            tid = int(tid)
        except Exception:
            continue
        out[tid] = {
            "rank": row.get("rank"),
            "points": row.get("points"),
            "goalsDiff": row.get("goalsDiff"),
            "form": row.get("form"),
        }
    return out


def fetch_odds_1x2(fixture_id: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Robosztus: megpróbálja kikeresni a 1/X/2 decimal odds-ot.
    Ha nincs hozzáférésed, visszaad (None,None,None)-t.
    """
    data = _get("/odds", {"fixture": fixture_id})
    resp = data.get("response") or []
    if not resp:
        return None, None, None

    # keresünk valami “Match Winner / 1X2” bet-et
    o1 = ox = o2 = None

    def try_set(label: str, val: Any):
        nonlocal o1, ox, o2
        try:
            v = float(val)
        except Exception:
            return
        l = _norm_name(label)
        if l in ("home", "1", "hazai", "hazai gyozelem"):
            o1 = o1 or v
        elif l in ("draw", "x", "dontetlen"):
            ox = ox or v
        elif l in ("away", "2", "vendeg", "vendeg gyozelem"):
            o2 = o2 or v

    for block in resp:
        bookmakers = block.get("bookmakers") or []
        for bm in bookmakers:
            bets = bm.get("bets") or []
            for bet in bets:
                name = _norm_name(bet.get("name") or "")
                # tipikus: "match winner"
                if "winner" not in name and "1x2" not in name and "match" not in name:
                    continue
                values = bet.get("values") or []
                for v in values:
                    try_set(v.get("value") or "", v.get("odd"))

        if o1 and ox and o2:
            break

    return o1, ox, o2
