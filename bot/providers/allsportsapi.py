import os
import time
from typing import Any, Dict, List, Optional

import requests

BASE_URL = (os.getenv("ALLSPORTSAPI_BASE_URL") or "https://apiv2.allsportsapi.com").rstrip("/")
SPORT = (os.getenv("ALLSPORTSAPI_SPORT") or "football").strip() or "football"


def _key() -> str:
    k = (os.getenv("ALLSPORTSAPI_KEY") or "").strip()
    if not k:
        raise RuntimeError("ALLSPORTSAPI_KEY nincs beállítva (GitHub Secrets).")
    return k


def _timeout() -> int:
    try:
        return int(os.getenv("ALLSPORTSAPI_TIMEOUT", "25"))
    except Exception:
        return 25


def _get(params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}/{SPORT}/"
    p = dict(params or {})
    p["APIkey"] = _key()

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=p, timeout=_timeout())
            if r.status_code != 200:
                raise RuntimeError(f"AllSportsAPI HTTP {r.status_code}: {r.text[:400]}")
            data = r.json() or {}
            return data
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)

    raise RuntimeError(f"AllSportsAPI request failed: {repr(last_err)}")


def fixtures_between(date_from: str, date_to: str, timezone: str = "Europe/Berlin") -> List[Dict[str, Any]]:
    data = _get({"met": "Fixtures", "from": date_from, "to": date_to, "timezone": timezone})
    if int(data.get("success") or 0) != 1:
        return []
    res = data.get("result")
    return res if isinstance(res, list) else []


def fixture_by_id(event_key: int, timezone: str = "Europe/Berlin") -> Optional[Dict[str, Any]]:
    data = _get({"met": "Fixtures", "matchId": str(int(event_key)), "timezone": timezone})
    if int(data.get("success") or 0) != 1:
        return None
    res = data.get("result")
    if isinstance(res, list) and res:
        return res[0]
    if isinstance(res, dict):
        return res
    return None
