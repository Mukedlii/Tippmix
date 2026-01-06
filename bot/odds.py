import os
from typing import Any, Dict, Optional
import requests

SPORTMONKS_API_TOKEN = (os.getenv("SPORTMONKS_API_TOKEN") or "").strip()

# SportMonks: Fulltime Result (1X2) market id = 1
SPORTMONKS_1X2_MARKET_ID = 1

def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(str(x).strip())
    except Exception:
        return None

def fetch_sportmonks_1x2_odds(fixture_id: int) -> Optional[Dict[str, float]]:
    """
    SportMonks pre-match odds 1X2 (market 1).
    Vissza: {"1": 2.10, "X": 3.40, "2": 3.60} vagy None
    """
    if not SPORTMONKS_API_TOKEN:
        return None

    url = f"https://api.sportmonks.com/v3/football/odds/pre-match/fixtures/{fixture_id}/markets/{SPORTMONKS_1X2_MARKET_ID}"
    params = {"api_token": SPORTMONKS_API_TOKEN}

    r = requests.get(url, params=params, timeout=25)
    if r.status_code != 200:
        return None

    data = r.json() or {}
    rows = data.get("data") or []
    if not isinstance(rows, list) or not rows:
        return None

    out: Dict[str, float] = {}
    # Több bookmaker is jöhet -> a "legjobb" oddsot vesszük (max), hogy a kifizetés ne legyen kamu alacsony
    best_1 = best_x = best_2 = None

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("stopped") is True:
            continue

        label = str(row.get("label") or row.get("name") or "").strip().lower()
        val = _safe_float(row.get("value"))
        if not val or val <= 1.01:
            continue

        # label mapping: gyakori formák: "1", "x", "2" vagy "Home", "Draw", "Away"
        if label in ("1", "home", "hazai"):
            best_1 = val if best_1 is None else max(best_1, val)
        elif label in ("x", "draw", "döntetlen", "dontetlen"):
            best_x = val if best_x is None else max(best_x, val)
        elif label in ("2", "away", "vendeg", "vendég"):
            best_2 = val if best_2 is None else max(best_2, val)

    if best_1:
        out["1"] = best_1
    if best_x:
        out["X"] = best_x
    if best_2:
        out["2"] = best_2

    return out if out else None
