import os
from typing import Any, Dict, Optional
import requests

API_FOOTBALL_KEY = (os.getenv("SPORTS_API_KEY") or "").strip()

_API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

# egyszerű futás-cache
_ODDS_CACHE: Dict[int, Dict[str, float]] = {}


def _headers() -> Dict[str, str]:
    if not API_FOOTBALL_KEY:
        raise RuntimeError("SPORTS_API_KEY nincs beállítva.")
    return {"x-apisports-key": API_FOOTBALL_KEY}


def fetch_api_football_1x2_odds(fixture_id: int) -> Dict[str, float]:
    """
    API-FOOTBALL odds lekérés (1X2 / Match Winner).

    Visszaad: {"1": 2.02, "X": 3.80, "2": 3.15} vagy {} ha nincs / nem található.
    """
    try:
        fid = int(fixture_id)
    except Exception:
        return {}

    if fid in _ODDS_CACHE:
        return _ODDS_CACHE[fid]

    try:
        url = f"{_API_FOOTBALL_BASE}/odds"
        r = requests.get(url, headers=_headers(), params={"fixture": fid}, timeout=25)
        if r.status_code != 200:
            _ODDS_CACHE[fid] = {}
            return {}

        data = r.json() or {}
        resp = data.get("response") or []
        if not resp:
            _ODDS_CACHE[fid] = {}
            return {}

        best: Dict[str, float] = {}

        # Keressük a "Match Winner"/"Match Result"/"1X2" jellegű piacot.
        for item in resp:
            for bm in (item.get("bookmakers") or []):
                for bet in (bm.get("bets") or []):
                    name = (bet.get("name") or "").lower()
                    if ("match winner" in name) or ("match result" in name) or (name.strip() == "1x2"):
                        tmp: Dict[str, float] = {}
                        for v in (bet.get("values") or []):
                            val = (v.get("value") or "").strip()
                            odd_raw = v.get("odd")
                            try:
                                odd = float(odd_raw)
                            except Exception:
                                continue

                            # különböző elnevezések
                            if val in ("Home", "1"):
                                tmp["1"] = odd
                            elif val in ("Draw", "X"):
                                tmp["X"] = odd
                            elif val in ("Away", "2"):
                                tmp["2"] = odd

                        if tmp.get("1") and tmp.get("X") and tmp.get("2"):
                            best = tmp
                            break
                if best:
                    break
            if best:
                break

        _ODDS_CACHE[fid] = best or {}
        return _ODDS_CACHE[fid]

    except Exception:
        _ODDS_CACHE[fid] = {}
        return {}
