import os
import time
from typing import Any, Dict, Optional
import requests

BASE_URL = "https://api.football-data.org/v4"


def _token() -> str:
    t = (os.getenv("FOOTBALL_DATA_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("FOOTBALL_DATA_TOKEN nincs beállítva (GitHub Secrets).")
    return t


def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Dict[str, Any]:
    headers = {"X-Auth-Token": _token()}
    url = f"{BASE_URL}{path}"

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"football-data HTTP {r.status_code}: {r.text[:600]}")
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"football-data request failed: {repr(last_err)}")


# Egyszerű mapping – bővíthető
LEAGUE_NAME_TO_CODE = {
    "premier league": "PL",
    "la liga": "PD",
    "primera division": "PD",
    "serie a": "SA",
    "bundesliga": "BL1",
    "ligue 1": "FL1",
    "eredivisie": "DED",
    "primeira liga": "PPL",
    "scottish premiership": "SPL",
    "championship": "ELC",
}


def guess_competition_code(league_name: str) -> Optional[str]:
    key = (league_name or "").strip().lower()
    for k, v in LEAGUE_NAME_TO_CODE.items():
        if k in key:
            return v
    return None


def get_standings_for_comp(code: str) -> Dict[str, Any]:
    return _get(f"/competitions/{code}/standings")
