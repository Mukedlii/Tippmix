import os
from typing import Any, Dict, Optional

import requests

API_FOOTBALL_KEY = (os.getenv("SPORTS_API_KEY") or "").strip()
DEBUG = (os.getenv("TIPPMIX_ODDS_DEBUG") or "0").lower() in ("1", "true", "yes")


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def fetch_api_football_1x2_odds(fixture_id: int) -> Optional[Dict[str, float]]:
    """
    API-FOOTBALL odds lekérés fixture ID alapján.
    Vissza: {"1": 2.1, "X": 3.3, "2": 3.6} vagy None

    Megjegyzés: csomag/limit függő. Ha nem elérhető, None.
    """
    if not API_FOOTBALL_KEY:
        if DEBUG:
            print("[odds] SPORTS_API_KEY nincs beállítva.")
        return None

    url = "https://v3.football.api-sports.io/odds"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"fixture": int(fixture_id)}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
    except Exception as e:
        if DEBUG:
            print(f"[odds] request error fixture={fixture_id}: {repr(e)}")
        return None

    if r.status_code != 200:
        if DEBUG:
            print(f"[odds] HTTP {r.status_code} fixture={fixture_id}: {r.text[:300]}")
        return None

    try:
        data = r.json() or {}
    except Exception as e:
        if DEBUG:
            print(f"[odds] JSON parse error fixture={fixture_id}: {repr(e)}")
        return None

    resp = data.get("response") or []
    if not resp:
        return None

    best_1 = best_x = best_2 = None

    for row in resp:
        bookmakers = row.get("bookmakers") or []
        for bm in bookmakers:
            bets = bm.get("bets") or []
            for bet in bets:
                bet_name = str(bet.get("name") or "").lower()
                if ("match winner" not in bet_name) and ("1x2" not in bet_name) and ("fulltime result" not in bet_name):
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

    if DEBUG:
        print(f"[odds] fixture={fixture_id} parsed={out if out else None}")

    return out if out else None
