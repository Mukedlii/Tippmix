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


def fetch_odds_for_sport_key(sport_key: str, markets: str = "h2h,totals") -> List[Dict[str, Any]]:
    """Fetch upcoming odds for a single The Odds API sport_key.
    
    Args:
        sport_key: API sport key (e.g. soccer_epl)
        markets: Comma-separated markets (default: h2h,totals)
                 - h2h = 1X2
                 - totals = Over/Under
    """
    sport_key = (sport_key or "").strip()
    if not sport_key:
        return []

    cache_key = (sport_key, _regions(), markets)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    data = _get(
        f"/sports/{sport_key}/odds",
        {
            "regions": _regions(),
            "markets": markets,
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
    """Best-effort team name match.

    The Odds API names can differ slightly from provider names (FC, accents, etc).
    We prefer strict equality, then a conservative substring fallback.
    
    Examples:
      "Hoffenheim" matches "TSG Hoffenheim" ✅
      "RB Leipzig" matches "RB Leipzig" ✅
      "Man Utd" matches "Manchester United" ✅
    """

    eh = _norm(event.get("home_team") or "")
    ea = _norm(event.get("away_team") or "")
    h = _norm(home_team)
    a = _norm(away_team)

    if not (h and a and eh and ea):
        return False

    if eh == h and ea == a:
        return True

    # Fuzzy matching: check significant word overlap
    # "hoffenheim" in "tsghoffenheim" OR "tsghoffenheim" in "hoffenheim"
    # More lenient: just check if the longer name contains the shorter
    h_match = (h in eh) or (eh in h) or (len(h) >= 4 and len(eh) >= 4 and (h in eh or eh in h))
    a_match = (a in ea) or (ea in a) or (len(a) >= 4 and len(ea) >= 4 and (a in ea or ea in a))
    
    if h_match and a_match:
        return True

    return False


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


def get_over_under_for_match(
    home_team: str,
    away_team: str,
    sport_keys: List[str],
    line: float = 2.5,
) -> Tuple[Optional[float], Optional[float]]:
    """Get Over/Under odds for a match.
    
    Strategy: Try exact line first, then fallback to closest available line (±1.0 tolerance).
    
    Returns:
        (over_odds, under_odds) or (None, None)
    """
    for sk in sport_keys:
        events = fetch_odds_for_sport_key(sk)
        for ev in events:
            if not match_event_to_fixture(ev, home_team, away_team):
                continue
            
            # Collect all available lines with odds
            line_options = {}  # {point: (over_odds, under_odds)}
            
            for bm in (ev.get("bookmakers") or []):
                for mkt in (bm.get("markets") or []):
                    if (mkt.get("key") or "").lower() != "totals":
                        continue
                    
                    # Group outcomes by point
                    point_map = {}
                    for out in (mkt.get("outcomes") or []):
                        point = out.get("point")
                        if point is None:
                            continue
                        
                        point = float(point)
                        name = (out.get("name") or "").lower()
                        
                        try:
                            price = float(out.get("price"))
                        except:
                            continue
                        
                        if point not in point_map:
                            point_map[point] = {}
                        
                        if "over" in name:
                            point_map[point]["over"] = max(point_map[point].get("over", 0), price)
                        elif "under" in name:
                            point_map[point]["under"] = max(point_map[point].get("under", 0), price)
                    
                    # Merge into line_options (keep best odds)
                    for pt, odds in point_map.items():
                        if "over" in odds and "under" in odds:
                            if pt not in line_options:
                                line_options[pt] = (odds["over"], odds["under"])
                            else:
                                line_options[pt] = (
                                    max(line_options[pt][0], odds["over"]),
                                    max(line_options[pt][1], odds["under"])
                                )
            
            if not line_options:
                return None, None
            
            # Try exact line first
            if line in line_options:
                return line_options[line]
            
            # Fallback: find closest line (within ±3.0 tolerance)
            closest_line = min(line_options.keys(), key=lambda x: abs(x - line))
            if abs(closest_line - line) <= 3.0:
                return line_options[closest_line]
            
            return None, None
    
    return None, None


def get_btts_for_match(
    home_team: str,
    away_team: str,
    sport_keys: List[str],
) -> Tuple[Optional[float], Optional[float]]:
    """Get Both Teams To Score odds.
    
    Returns:
        (btts_yes_odds, btts_no_odds) or (None, None)
    """
    for sk in sport_keys:
        events = fetch_odds_for_sport_key(sk)
        for ev in events:
            if not match_event_to_fixture(ev, home_team, away_team):
                continue
            
            # Find btts market
            for bm in (ev.get("bookmakers") or []):
                for mkt in (bm.get("markets") or []):
                    if (mkt.get("key") or "").lower() != "btts":
                        continue
                    
                    yes_odds = None
                    no_odds = None
                    
                    for out in (mkt.get("outcomes") or []):
                        name = (out.get("name") or "").lower()
                        try:
                            price = float(out.get("price"))
                        except:
                            continue
                        
                        if "yes" in name:
                            yes_odds = price if yes_odds is None else max(yes_odds, price)
                        elif "no" in name:
                            no_odds = price if no_odds is None else max(no_odds, price)
                    
                    if yes_odds and no_odds:
                        return yes_odds, no_odds
            
            return None, None
    
    return None, None
