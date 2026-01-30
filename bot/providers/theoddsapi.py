import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://api.the-odds-api.com/v4"

# Very small in-process cache (per run)
_CACHE: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}


def _key() -> str:
    k = (os.getenv("ODDS_API_KEY") or "").strip()
    if not k:
        raise RuntimeError("ODDS_API_KEY nincs beállítva")
    return k


def _regions() -> str:
    return (os.getenv("ODDS_REGIONS") or "eu").strip() or "eu"


def _timeout() -> int:
    try:
        return int(os.getenv("ODDS_TIMEOUT", "25"))
    except Exception:
        return 25


def _get(path: str, params: Dict[str, Any], timeout: Optional[int] = None) -> Any:
    url = f"{BASE_URL}{path}"
    p = dict(params or {})
    p["apiKey"] = _key()

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=p, timeout=timeout or _timeout())
            if r.status_code != 200:
                raise RuntimeError(f"TheOddsAPI HTTP {r.status_code}: {r.text[:400]}")
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"TheOddsAPI request failed: {repr(last_err)}")


def _norm(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


def _extract_best_h2h(event: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return best decimal odds for (home, draw, away) across bookmakers."""
    home = _norm(event.get("home_team") or "")
    away = _norm(event.get("away_team") or "")

    best_home: Optional[float] = None
    best_draw: Optional[float] = None
    best_away: Optional[float] = None

    for bm in (event.get("bookmakers") or []):
        for mkt in (bm.get("markets") or []):
            if (mkt.get("key") or "").lower() != "h2h":
                continue
            for out in (mkt.get("outcomes") or []):
                name = _norm(out.get("name") or "")
                try:
                    price = float(out.get("price"))
                except Exception:
                    continue

                if name == "draw" or name == "x":
                    best_draw = price if best_draw is None else max(best_draw, price)
                    continue

                if home and name == home:
                    best_home = price if best_home is None else max(best_home, price)
                elif away and name == away:
                    best_away = price if best_away is None else max(best_away, price)

    return best_home, best_draw, best_away


def fetch_odds_for_sport_key(sport_key: str) -> List[Dict[str, Any]]:
    """Fetch upcoming H2H odds for a single The Odds API sport_key."""
    sport_key = (sport_key or "").strip()
    if not sport_key:
        return []

    cache_key = (sport_key, _regions(), "h2h")
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    data = _get(
        f"/sports/{sport_key}/odds",
        {
            "regions": _regions(),
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        },
    )

    if not isinstance(data, list):
        _CACHE[cache_key] = []
        return []

    _CACHE[cache_key] = data
    return data


def match_event_to_fixture(
    event: Dict[str, Any],
    home_team: str,
    away_team: str,
) -> bool:
    eh = _norm(event.get("home_team") or "")
    ea = _norm(event.get("away_team") or "")
    h = _norm(home_team)
    a = _norm(away_team)
    return bool(h and a and eh == h and ea == a)


def get_1x2_for_match(
    home_team: str,
    away_team: str,
    sport_keys: List[str],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Try multiple sport_keys until a match is found; returns (o1, ox, o2)."""
    for sk in sport_keys:
        events = fetch_odds_for_sport_key(sk)
        for ev in events:
            if match_event_to_fixture(ev, home_team, away_team):
                return _extract_best_h2h(ev)
    return None, None, None
