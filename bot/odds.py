import os
from typing import Any, Dict, Optional

import requests

SPORTMONKS_API_TOKEN = (os.getenv("SPORTMONKS_API_TOKEN") or "").strip()

# SportMonks: Fulltime Result (1X2) market id = 1
SPORTMONKS_1X2_MARKET_ID = 1

# Debug ki/be (GitHub Actions logba)
DEBUG = (os.getenv("SPORTMONKS_DEBUG") or "0").lower() in ("1", "true", "yes")


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

    FIGYELEM:
    - fixture_id-nek SportMonks fixture ID-nak kell lennie.
    - Ha te API-Sports fixture ID-t adsz ide, akkor gyakran None lesz.
    """
    if not SPORTMONKS_API_TOKEN:
        if DEBUG:
            print("[SPORTMONKS] Nincs SPORTMONKS_API_TOKEN beállítva.")
        return None

    url = (
        f"https://api.sportmonks.com/v3/football/odds/pre-match/"
        f"fixtures/{fixture_id}/markets/{SPORTMONKS_1X2_MARKET_ID}"
    )
    params = {"api_token": SPORTMONKS_API_TOKEN}

    if DEBUG:
        print(f"[SPORTMONKS] odds lookup fixture_id={fixture_id} url={url}")

    try:
        r = requests.get(url, params=params, timeout=25)
    except Exception as e:
        if DEBUG:
            print("[SPORTMONKS] request error:", repr(e))
        return None

    if DEBUG:
        print(f"[SPORTMONKS] HTTP {r.status_code}")

    if r.status_code != 200:
        if DEBUG:
            print("[SPORTMONKS] non-200 body:", r.text[:500])
        return None

    try:
        data = r.json() or {}
    except Exception as e:
        if DEBUG:
            print("[SPORTMONKS] JSON parse error:", repr(e))
            print("[SPORTMONKS] raw body:", r.text[:500])
        return None

    if DEBUG:
        print("[SPORTMONKS] response keys:", list(data.keys()))
        # ne dumpold ki az egész body-t, csak a data elemek számát
        rows = data.get("data") or []
        print("[SPORTMONKS] data rows:", len(rows) if isinstance(rows, list) else "not-a-list")

    rows = data.get("data") or []
    if not isinstance(rows, list) or not rows:
        return None

    # Több bookmaker / sor jöhet, a "legjobb" oddsot vesszük (max)
    best_1: Optional[float] = None
    best_x: Optional[float] = None
    best_2: Optional[float] = None

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

    out: Dict[str, float] = {}
    if best_1 is not None:
        out["1"] = best_1
    if best_x is not None:
        out["X"] = best_x
    if best_2 is not None:
        out["2"] = best_2

    if DEBUG:
        print("[SPORTMONKS] parsed odds:", out if out else "None")

    return out if out else None
