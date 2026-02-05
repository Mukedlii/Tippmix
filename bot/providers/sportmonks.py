import os
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import requests

BASE = "https://api.sportmonks.com/v3/football"
BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def _token() -> str:
    t = (os.getenv("SPORTMONKS_API_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("SPORTMONKS_API_TOKEN nincs beállítva (GitHub Secrets).")
    return t


def _get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Dict[str, Any]:
    p = dict(params or {})
    p["api_token"] = _token()

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=p, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"SportMonks HTTP {r.status_code}: {r.text[:600]}")
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise RuntimeError(f"SportMonks request failed: {repr(last_err)}")


def _norm(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


def get_fixture_by_id(fixture_id: int, include_scores: bool = False) -> Optional[Dict[str, Any]]:
    url = f"{BASE}/fixtures/{int(fixture_id)}"
    inc = ["participants", "league"]
    if include_scores:
        inc.append("scores")
    data = _get(url, {"include": ";".join(inc), "per_page": 1})
    # response shape: {data:{...}}
    fx = data.get("data")
    return fx if isinstance(fx, dict) else None


def fixtures_between(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """
    GET /fixtures/between/{from}/{to} + pagination
    """
    url = f"{BASE}/fixtures/between/{date_from}/{date_to}"
    page = 1
    out: List[Dict[str, Any]] = []
    while True:
        data = _get(url, {"include": "participants;league", "per_page": 100, "page": page})
        out.extend(data.get("data") or [])
        pag = data.get("pagination") or {}
        if not pag.get("has_more"):
            break
        page = (pag.get("current_page") or page) + 1
        if page > 20:
            break
    return out


def build_fixture_index(fixtures: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], int]:
    """
    kulcs: (YYYY-MM-DD, norm_home, norm_away) -> sportmonks_fixture_id
    """
    idx: Dict[Tuple[str, str, str], int] = {}
    for fx in fixtures:
        fid = fx.get("id")
        try:
            fid = int(fid)
        except Exception:
            continue

        starting = str(fx.get("starting_at") or "")
        try:
            dt = datetime.datetime.fromisoformat(starting.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            dt = dt.astimezone(BUDAPEST_TZ)
            d = dt.date().isoformat()
        except Exception:
            continue

        parts = fx.get("participants") or []
        home = away = None
        for p in parts:
            meta = p.get("meta") or {}
            loc = (meta.get("location") or "").lower()
            if loc == "home":
                home = p.get("name")
            elif loc == "away":
                away = p.get("name")
        if not home or not away:
            if len(parts) >= 2:
                home = home or parts[0].get("name")
                away = away or parts[1].get("name")
        if not home or not away:
            continue

        idx[(d, _norm(home), _norm(away))] = fid
    return idx


def prematch_odds_fixture(fixture_id: int) -> List[Dict[str, Any]]:
    url = f"{BASE}/odds/pre-match/fixtures/{fixture_id}"
    data = _get(url, {"per_page": 200})
    return data.get("data") or []


def extract_1x2(odds_items: List[Dict[str, Any]], home_team: str, away_team: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
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

        if "draw" in n or n == "x":
            draw_vals.append(v)
            continue
        if home_key and home_key in n:
            home_vals.append(v)
            continue
        if away_key and away_key in n:
            away_vals.append(v)
            continue
        if n in ("1", "home"):
            home_vals.append(v)
        elif n in ("2", "away"):
            away_vals.append(v)

    def med(xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        xs = sorted(xs)
        mid = len(xs) // 2
        return xs[mid] if len(xs) % 2 == 1 else (xs[mid - 1] + xs[mid]) / 2.0

    return med(home_vals), med(draw_vals), med(away_vals)
