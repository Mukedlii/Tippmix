import os
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

BUDAPEST_TZ = ZoneInfo("Europe/Budapest")

# -----------------------
# ENV
# -----------------------
SPORTS_API_KEY = (os.getenv("SPORTS_API_KEY") or "").strip()
SPORTS_API_BASE = (os.getenv("SPORTS_API_BASE_URL") or "https://v3.football.api-sports.io").rstrip("/")
SPORTS_API_TIMEZONE = os.getenv("SPORTS_API_TIMEZONE", "Europe/Budapest")

FOOTBALL_DATA_TOKEN = (os.getenv("FOOTBALL_DATA_TOKEN") or "").strip()

SPORTMONKS_API_TOKEN = (os.getenv("SPORTMONKS_API_TOKEN") or "").strip()
SPORTMONKS_BASE = "https://api.sportmonks.com/v3/football"

TIPPMIX_ENRICH_LIMIT = int(os.getenv("TIPPMIX_ENRICH_LIMIT", "40"))
TIPPMIX_MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
TIPPMIX_MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))

EXCLUDE_YOUTH = os.getenv("TIPPMIX_EXCLUDE_YOUTH", "1").lower() in ("1", "true", "yes")


# -----------------------
# Helpers
# -----------------------
def _sleep_backoff(attempt: int) -> None:
    time.sleep(0.5 * attempt)


def _dt_from_iso(s: str) -> Optional[datetime.datetime]:
    try:
        dt = datetime.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return dt
    except Exception:
        return None


def _extract_hour(iso_str: str) -> Optional[int]:
    dt = _dt_from_iso(iso_str)
    if not dt:
        return None
    return dt.hour


def _slot_filter(matches: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()
    out: List[Dict[str, Any]] = []
    for m in matches:
        h = _extract_hour(str(m.get("kickoff_local") or ""))
        if h is None:
            continue
        if slot == "DAY":
            if 9 <= h < 16:
                out.append(m)
        else:
            if 16 <= h <= 23:
                out.append(m)
    return out


def _is_bad_league(league_name: str) -> bool:
    name = (league_name or "").upper()
    bad = ["FRIENDLY", "U20", "U19", "U18", "YOUTH", "U23", "RESERVE", "B TEAM", "B-T"]
    return any(x in name for x in bad)


def _norm_team(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


# -----------------------
# API-Sports (SportAPI) client
# -----------------------
def _sports_get(path: str, params: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    if not SPORTS_API_KEY:
        raise RuntimeError("SPORTS_API_KEY nincs beállítva (GitHub Secrets).")

    headers = {"x-apisports-key": SPORTS_API_KEY}
    url = f"{SPORTS_API_BASE}{path}"

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"API-Sports HTTP {r.status_code}: {r.text[:800]}")
            return r.json()
        except Exception as e:
            last_err = e
            _sleep_backoff(attempt)
    raise RuntimeError(f"API-Sports request failed: {repr(last_err)}")


def _sports_fetch_fixtures(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    data = _sports_get("/fixtures", {"from": date_from, "to": date_to, "timezone": SPORTS_API_TIMEZONE})
    return data.get("response") or []


def _sports_parse_fixture(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fx = raw.get("fixture") or {}
        lg = raw.get("league") or {}
        teams = raw.get("teams") or {}

        fixture_id = int(fx.get("id"))
        kickoff = fx.get("date")
        league_id = int(lg.get("id")) if lg.get("id") is not None else None
        season = int(lg.get("season")) if lg.get("season") is not None else None

        league_name = lg.get("name") or "Ismeretlen liga"
        country = lg.get("country") or ""

        home = teams.get("home") or {}
        away = teams.get("away") or {}
        home_id = int(home.get("id")) if home.get("id") is not None else None
        away_id = int(away.get("id")) if away.get("id") is not None else None

        return {
            "sport": "football",
            "fixture_id": fixture_id,
            "league_id": league_id,
            "season": season,
            "league_name": str(league_name),
            "country_name": str(country),
            "kickoff_local": str(kickoff),

            "home_team_id": home_id,
            "away_team_id": away_id,
            "home_team": home.get("name") or "Hazai csapat",
            "away_team": away.get("name") or "Vendég csapat",

            # enrichment mezők
            "standings": None,   # {"home": {...}, "away": {...}}
            "injuries": None,    # lista
            "odds": {"1": None, "X": None, "2": None},
        }
    except Exception:
        return None


def _sports_fetch_injuries(fixture_id: int) -> List[Dict[str, Any]]:
    data = _sports_get("/injuries", {"fixture": fixture_id, "timezone": SPORTS_API_TIMEZONE})
    resp = data.get("response") or []
    out: List[Dict[str, Any]] = []
    for it in resp:
        out.append({
            "player": ((it.get("player") or {}).get("name") or ""),
            "team": ((it.get("team") or {}).get("name") or ""),
            "reason": (it.get("reason") or ""),
        })
    return out


def _sports_fetch_standings(league_id: int, season: int) -> Dict[int, Dict[str, Any]]:
    data = _sports_get("/standings", {"league": league_id, "season": season})
    resp = data.get("response") or []
    if not resp:
        return {}

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


def _sports_fetch_odds_1x2(fixture_id: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Visszaadja az 1/X/2 decimal oddst, ha elérhető.
    Ha a csomagod nem engedi oddsot, (None, None, None).
    """
    try:
        data = _sports_get("/odds", {"fixture": fixture_id})
    except Exception:
        return None, None, None

    resp = data.get("response") or []
    if not resp:
        return None, None, None

    o1 = ox = o2 = None

    def _try_set(label: str, val: Any):
        nonlocal o1, ox, o2
        try:
            v = float(val)
        except Exception:
            return
        lab = (label or "").strip().lower()
        if lab in ("home", "1"):
            o1 = o1 or v
        elif lab in ("draw", "x"):
            ox = ox or v
        elif lab in ("away", "2"):
            o2 = o2 or v

    for block in resp:
        bookmakers = block.get("bookmakers") or []
        for bm in bookmakers:
            bets = bm.get("bets") or []
            for bet in bets:
                name = (bet.get("name") or "").lower()
                if "winner" not in name and "1x2" not in name and "match" not in name:
                    continue
                values = bet.get("values") or []
                for v in values:
                    _try_set(v.get("value") or "", v.get("odd"))
        if o1 and ox and o2:
            break

    return o1, ox, o2


# -----------------------
# Football-Data backup pool
# -----------------------
def _football_data_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Dict[str, Any]:
    if not FOOTBALL_DATA_TOKEN:
        raise RuntimeError("FOOTBALL_DATA_TOKEN nincs beállítva (GitHub Secrets).")
    url = f"https://api.football-data.org/v4{path}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"football-data HTTP {r.status_code}: {r.text[:800]}")
            return r.json()
        except Exception as e:
            last_err = e
            _sleep_backoff(attempt)
    raise RuntimeError(f"football-data request failed: {repr(last_err)}")


def _football_data_pool(days_ahead: int) -> List[Dict[str, Any]]:
    now = datetime.datetime.now(BUDAPEST_TZ)
    start = now.date()
    end = start + datetime.timedelta(days=days_ahead)

    data = _football_data_get("/matches", {"dateFrom": start.isoformat(), "dateTo": end.isoformat()})
    matches = data.get("matches") or []
    out: List[Dict[str, Any]] = []

    for it in matches:
        try:
            fixture_id = int(it.get("id"))
        except Exception:
            continue

        comp = it.get("competition") or {}
        home = it.get("homeTeam") or {}
        away = it.get("awayTeam") or {}

        kickoff_utc = it.get("utcDate")
        dt = _dt_from_iso(str(kickoff_utc))
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            dt = dt.astimezone(BUDAPEST_TZ)
            kickoff_local = dt.isoformat()
        else:
            kickoff_local = str(kickoff_utc)

        out.append({
            "sport": "football",
            "fixture_id": fixture_id,
            "league_id": None,
            "season": None,
            "league_name": comp.get("name") or "football-data",
            "country_name": "",
            "kickoff_local": kickoff_local,
            "home_team_id": home.get("id"),
            "away_team_id": away.get("id"),
            "home_team": home.get("name") or "Hazai csapat",
            "away_team": away.get("name") or "Vendég csapat",
            "standings": None,
            "injuries": None,
            "odds": {"1": None, "X": None, "2": None},
        })

    return out


# -----------------------
# SportMonks odds backup
# -----------------------
def _sportmonks_get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 25) -> Dict[str, Any]:
    if not SPORTMONKS_API_TOKEN:
        raise RuntimeError("SPORTMONKS_API_TOKEN nincs beállítva (GitHub Secrets).")

    p = dict(params or {})
    p["api_token"] = SPORTMONKS_API_TOKEN

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=p, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"SportMonks HTTP {r.status_code}: {r.text[:800]}")
            return r.json()
        except Exception as e:
            last_err = e
            _sleep_backoff(attempt)
    raise RuntimeError(f"SportMonks request failed: {repr(last_err)}")


def _sportmonks_fixtures_between(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    url = f"{SPORTMONKS_BASE}/fixtures/between/{date_from}/{date_to}"
    page = 1
    out: List[Dict[str, Any]] = []
    while True:
        data = _sportmonks_get(url, {"include": "participants;league", "per_page": 100, "page": page})
        out.extend(data.get("data") or [])
        pag = data.get("pagination") or {}
        if not pag.get("has_more"):
            break
        page = (pag.get("current_page") or page) + 1
        if page > 20:
            break
    return out


def _sportmonks_build_index(fixtures: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], int]:
    idx: Dict[Tuple[str, str, str], int] = {}
    for fx in fixtures:
        fid = fx.get("id")
        try:
            fid = int(fid)
        except Exception:
            continue

        starting = str(fx.get("starting_at") or "")
        dt = _dt_from_iso(starting)
        if not dt:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        dt = dt.astimezone(BUDAPEST_TZ)
        d = dt.date().isoformat()

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

        idx[(d, _norm_team(home), _norm_team(away))] = fid

    return idx


def _sportmonks_prematch_odds(fixture_id: int) -> List[Dict[str, Any]]:
    url = f"{SPORTMONKS_BASE}/odds/pre-match/fixtures/{fixture_id}"
    data = _sportmonks_get(url, {"per_page": 200})
    return data.get("data") or []


def _sportmonks_extract_1x2(items: List[Dict[str, Any]], home_team: str, away_team: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    home_key = _norm_team(home_team)
    away_key = _norm_team(away_team)

    home_vals: List[float] = []
    draw_vals: List[float] = []
    away_vals: List[float] = []

    def _norm(s: str) -> str:
        return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()

    for it in items or []:
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


# -----------------------
# Main entry
# -----------------------
def fetch_matches_for_today(slot: str = "DAY") -> List[Dict[str, Any]]:
    """
    Garantált meccs-pool, amíg az API-k adnak adatot:
    - SportAPI: 1→2→3→5→7 napos pool, amíg >= (MIN_VIP+MIN_FREE) külön meccs nincs
    - ha kevés: Football-Data backup hozzáfűz
    - slotban kevés: nem dobjuk el, hanem poolból válogatunk és TIPPMIX_SLOT_NOTE-ot beállítunk
    - enrichment: standings + injuries + odds az első TIPPMIX_ENRICH_LIMIT meccsre
    """
    needed = max(30, TIPPMIX_MIN_VIP + TIPPMIX_MIN_FREE + 10)

    pool: List[Dict[str, Any]] = []

    # SportAPI pool bővítés
    for days in (1, 2, 3, 5, 7):
        try:
            now = datetime.datetime.now(BUDAPEST_TZ)
            start = now.date()
            end = start + datetime.timedelta(days=days)
            raw = _sports_fetch_fixtures(start.isoformat(), end.isoformat())
            tmp: List[Dict[str, Any]] = []
            for r in raw:
                m = _sports_parse_fixture(r)
                if m:
                    tmp.append(m)
            pool = tmp
            print(f"[matches] SportAPI fixtures: days={days} -> {len(pool)}")
        except Exception as e:
            print(f"[matches] SportAPI pool hiba days={days}: {repr(e)}")
            pool = []

        if len(pool) >= needed:
            break

    # Football-data backup ha kevés
    if len(pool) < needed and FOOTBALL_DATA_TOKEN:
        try:
            fb = _football_data_pool(7)
            seen = {m["fixture_id"] for m in pool if m.get("fixture_id") is not None}
            added = 0
            for m in fb:
                if m["fixture_id"] not in seen:
                    pool.append(m)
                    seen.add(m["fixture_id"])
                    added += 1
            print(f"[matches] football-data backup added={added}, total={len(pool)}")
        except Exception as e:
            print(f"[matches] football-data backup hiba: {repr(e)}")

    if not pool:
        return []

    # youth/friendly hátratolás (ha van elég)
    if EXCLUDE_YOUTH:
        good = [m for m in pool if not _is_bad_league(m.get("league_name") or "")]
        if len(good) >= 30:
            pool = good

    # slot filter (ha kevés: ne dobjuk el)
    slot_matches = _slot_filter(pool, slot)
    if len(slot_matches) < max(10, TIPPMIX_MIN_VIP + TIPPMIX_MIN_FREE):
        os.environ["TIPPMIX_SLOT_NOTE"] = "Kevés meccs ebben az idősávban, ezért a következő napokból válogattam."
        candidates = pool
    else:
        candidates = slot_matches

    # rendezés: data-rich meccsek előre
    def score(m: Dict[str, Any]) -> Tuple[int, int]:
        s = 0
        if m.get("league_id") and m.get("season"):
            s += 2
        if m.get("home_team_id") and m.get("away_team_id"):
            s += 2
        if not _is_bad_league(m.get("league_name") or ""):
            s += 1
        hour = _extract_hour(str(m.get("kickoff_local") or "")) or 99
        return (-s, hour)

    candidates.sort(key=score)

    # SportMonks odds index (backup), ha van token
    sm_index: Dict[Tuple[str, str, str], int] = {}
    if SPORTMONKS_API_TOKEN:
        try:
            now = datetime.datetime.now(BUDAPEST_TZ)
            d1 = now.date().isoformat()
            d2 = (now.date() + datetime.timedelta(days=7)).isoformat()
            sm_fx = _sportmonks_fixtures_between(d1, d2)
            sm_index = _sportmonks_build_index(sm_fx)
            print(f"[matches] SportMonks index size={len(sm_index)}")
        except Exception as e:
            print(f"[matches] SportMonks index hiba: {repr(e)}")
            sm_index = {}

    # enrichment első N meccsre
    enriched: List[Dict[str, Any]] = []
    standings_cache: Dict[Tuple[int, int], Dict[int, Dict[str, Any]]] = {}

    for m in candidates[:TIPPMIX_ENRICH_LIMIT]:
        fid = int(m["fixture_id"])

        # ODDS: SportAPI -> SportMonks fallback
        o1 = ox = o2 = None
        try:
            o1, ox, o2 = _sports_fetch_odds_1x2(fid)
        except Exception:
            pass

        if not (o1 and ox and o2) and sm_index:
            try:
                dt = _dt_from_iso(str(m.get("kickoff_local") or ""))
                if dt:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                    dt = dt.astimezone(BUDAPEST_TZ)
                    d = dt.date().isoformat()
                    key = (d, _norm_team(m["home_team"]), _norm_team(m["away_team"]))
                    sm_fid = sm_index.get(key)
                    if sm_fid:
                        items = _sportmonks_prematch_odds(sm_fid)
                        so1, sox, so2 = _sportmonks_extract_1x2(items, m["home_team"], m["away_team"])
                        o1, ox, o2 = o1 or so1, ox or sox, o2 or so2
            except Exception:
                pass

        m["odds"] = {"1": o1, "X": ox, "2": o2}

        # STANDINGS: cache-elve liga+szezon szerint
        standings_home = standings_away = None
        try:
            if m.get("league_id") and m.get("season"):
                key = (int(m["league_id"]), int(m["season"]))
                if key not in standings_cache:
                    standings_cache[key] = _sports_fetch_standings(key[0], key[1])
                table = standings_cache[key]
                if m.get("home_team_id") in table:
                    standings_home = table[m["home_team_id"]]
                if m.get("away_team_id") in table:
                    standings_away = table[m["away_team_id"]]
        except Exception:
            pass

        m["standings"] = {"home": standings_home, "away": standings_away}

        # INJURIES
        try:
            inj = _sports_fetch_injuries(fid)
        except Exception:
            inj = []
        m["injuries"] = inj[:10]

        enriched.append(m)

    enriched.extend(candidates[TIPPMIX_ENRICH_LIMIT:])

    print(f"[matches] final candidates={len(candidates)} enriched={len(enriched)} slot={slot}")
    return enriched
