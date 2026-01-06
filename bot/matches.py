import os
import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from bot.providers.api_sports import (
    fetch_fixtures,
    parse_fixture,
    fetch_injuries_by_fixture,
    fetch_standings,
    fetch_odds_1x2,
)
from bot.providers.football_data import guess_competition_code, get_standings_for_comp
from bot.providers.sportmonks import fixtures_between, build_fixture_index, prematch_odds_fixture, extract_1x2

BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def _extract_hour(iso_str: str) -> Optional[int]:
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.hour
    except Exception:
        return None


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


def _is_bad_league(m: Dict[str, Any]) -> bool:
    name = (m.get("league_name") or "").upper()
    bad = ["FRIENDLY", "U20", "U19", "U18", "YOUTH", "U23", "RESERVE"]
    return any(x in name for x in bad)


def fetch_matches_for_today(slot: str = "DAY") -> List[Dict[str, Any]]:
    """
    1) SportAPI: ma+holnap fixture pool (sok meccs)
    2) Slot szerinti szűrés, ha kevés -> 24-48 órából válogatunk
    3) Enrichment (dosszié): standings + injuries + odds
    """
    enrich_limit = int(os.getenv("TIPPMIX_ENRICH_LIMIT", "40"))

    now = datetime.datetime.now(BUDAPEST_TZ)
    today = now.date()
    tomorrow = today + datetime.timedelta(days=1)

    # 1) pool
    raw = fetch_fixtures(today.isoformat(), tomorrow.isoformat())
    base: List[Dict[str, Any]] = []
    for r in raw:
        m = parse_fixture(r)
        if m:
            base.append(m)

    # 2) slot
    slot_matches = _slot_filter(base, slot)
    if len(slot_matches) < 25:
        # ha kevés, kiterítjük 48 órára
        day2 = today + datetime.timedelta(days=2)
        raw2 = fetch_fixtures(today.isoformat(), day2.isoformat())
        base2: List[Dict[str, Any]] = []
        for r in raw2:
            m = parse_fixture(r)
            if m:
                base2.append(m)
        slot_matches = _slot_filter(base2, slot)
        if len(slot_matches) < 25:
            # végső: bármi a következő 48 órából
            os.environ["TIPPMIX_SLOT_NOTE"] = "Kevés meccs ebben az idősávban, ezért a következő 48 órából válogattam."
            slot_matches = base2

    # 3) ha sok meccs van, dobjuk hátra a gyengéket
    good = [m for m in slot_matches if not _is_bad_league(m)]
    if len(good) >= 40:
        pool = good
    else:
        pool = slot_matches

    # 4) előrang: ahol van liga_id/season/team_id
    def score(m: Dict[str, Any]) -> int:
        s = 0
        if m.get("league_id") and m.get("season"):
            s += 2
        if m.get("home_team_id") and m.get("away_team_id"):
            s += 2
        if not _is_bad_league(m):
            s += 1
        return -s

    pool.sort(key=score)

    # 5) SportMonks index egyszer (odds backup)
    date_from = today.isoformat()
    date_to = (today + datetime.timedelta(days=2)).isoformat()
    sm_fixtures = []
    sm_index = {}
    try:
        sm_fixtures = fixtures_between(date_from, date_to)
        sm_index = build_fixture_index(sm_fixtures)
    except Exception:
        sm_index = {}

    # 6) enrichment csak top N
    enriched: List[Dict[str, Any]] = []
    for m in pool[:enrich_limit]:
        fid = int(m["fixture_id"])

        # --- odds (SportAPI -> SportMonks fallback)
        try:
            o1, ox, o2 = fetch_odds_1x2(fid)
        except Exception:
            o1 = ox = o2 = None

        if not (o1 and ox and o2) and sm_index:
            # sportmonks map: date + team names
            try:
                kickoff = str(m.get("kickoff_local") or "")
                dt = datetime.datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                d = dt.date().isoformat()
                key = (d, "".join(ch.lower() for ch in m["home_team"] if ch.isalnum() or ch.isspace()).strip(),
                          "".join(ch.lower() for ch in m["away_team"] if ch.isalnum() or ch.isspace()).strip())
                sm_fid = sm_index.get(key)
                if sm_fid:
                    items = prematch_odds_fixture(sm_fid)
                    so1, sox, so2 = extract_1x2(items, m["home_team"], m["away_team"])
                    o1, ox, o2 = o1 or so1, ox or sox, o2 or so2
            except Exception:
                pass

        m["odds"] = {"1": o1, "X": ox, "2": o2}

        # --- standings (SportAPI -> football-data fallback top ligákra)
        standings_home = standings_away = None
        try:
            league_id = int(m["league_id"])
            season = int(m["season"])
            table = fetch_standings(league_id, season)
            if m.get("home_team_id") in table:
                standings_home = table[m["home_team_id"]]
            if m.get("away_team_id") in table:
                standings_away = table[m["away_team_id"]]
        except Exception:
            standings_home = standings_away = None

        if standings_home is None or standings_away is None:
            try:
                code = guess_competition_code(m.get("league_name") or "")
                if code:
                    st = get_standings_for_comp(code)
                    # football-data struktúráját itt csak “nyers” formában betesszük,
                    # az AI-nak elég a position/points/gd jelleg.
                    m["standings_fallback"] = st
            except Exception:
                pass

        m["standings"] = {"home": standings_home, "away": standings_away}

        # --- injuries (SportAPI)
        try:
            inj = fetch_injuries_by_fixture(fid)
        except Exception:
            inj = []
        # rövidítés: max 10 sor
        m["injuries"] = inj[:10]

        enriched.append(m)

    # a maradék meccseket (enrichment nélkül) is visszaadjuk, hogy legyen miből 6+ tippet választani
    rest = pool[enrich_limit:]
    return enriched + rest
