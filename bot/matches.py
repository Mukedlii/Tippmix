import os
import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from bot.sportmonks_client import (
    get_fixtures_for_date,
    get_prematch_odds_for_fixture,
    extract_home_away_participants,
    extract_league_name_country,
    extract_kickoff_local,
    extract_1x2_odds_from_sportmonks_odds,
)

BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
MAX_ODDS_LOOKUP = int(os.getenv("TIPPMIX_MAX_ODDS_LOOKUP", "80"))


def _extract_hour(kickoff_local_iso: str) -> Optional[int]:
    try:
        dt = datetime.datetime.fromisoformat(kickoff_local_iso.replace("Z", "+00:00"))
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


def fetch_matches_for_today(slot: str = "DAY") -> List[Dict[str, Any]]:
    """
    SportMonks: ma + holnap fixture lista, slot szerint válogatunk.
    Ha slotban kevés meccs van, akkor a következő 24 órából töltünk fel.
    """
    now_local = datetime.datetime.now(BUDAPEST_TZ)
    today = now_local.date()
    tomorrow = today + datetime.timedelta(days=1)

    # 1) Lekérjük ma és holnap fixtures
    fixtures_today = get_fixtures_for_date(today.isoformat())
    fixtures_tomorrow = get_fixtures_for_date(tomorrow.isoformat())
    fixtures = (fixtures_today or []) + (fixtures_tomorrow or [])

    raw_matches: List[Dict[str, Any]] = []
    for fx in fixtures:
        fid = fx.get("id")
        try:
            fid = int(fid)
        except Exception:
            continue

        home_team, away_team = extract_home_away_participants(fx)
        league_name, country_name = extract_league_name_country(fx)
        kickoff_local = extract_kickoff_local(fx)

        raw_matches.append(
            {
                "sport": "football",
                "fixture_id": fid,
                "league_name": league_name,
                "country_name": country_name,
                "kickoff_local": kickoff_local,
                "home_team": home_team,
                "away_team": away_team,
                "home_form": None,
                "home_avg_goals_for": None,
                "home_avg_goals_against": None,
                "away_form": None,
                "away_avg_goals_for": None,
                "away_avg_goals_against": None,
                "odds": {"1": None, "X": None, "2": None},
            }
        )

    # 2) Slot szűrés
    slot_matches = _slot_filter(raw_matches, slot)

    # 3) Ha üres / kevés, akkor legyen fallback: a következő 24 órából bármi
    if len(slot_matches) < 8:
        # jelzés a headerhez (openai_logic / main is fel tudja használni)
        os.environ["TIPPMIX_SLOT_NOTE"] = "Nincs elég meccs ebben az idősávban, ezért a következő 24 órából válogattam."
        slot_matches = raw_matches

    # 4) Odds hozzáadás (limitálva)
    enriched: List[Dict[str, Any]] = []
    looked_up = 0
    for m in slot_matches:
        if looked_up >= MAX_ODDS_LOOKUP:
            enriched.append(m)
            continue

        odds_items = get_prematch_odds_for_fixture(int(m["fixture_id"]))
        o1, ox, o2 = extract_1x2_odds_from_sportmonks_odds(odds_items, m["home_team"], m["away_team"])
        m["odds"]["1"] = o1
        m["odds"]["X"] = ox
        m["odds"]["2"] = o2

        looked_up += 1
        enriched.append(m)

    print(
        f"fetch_matches_for_today: total fixtures={len(raw_matches)}, slot={slot} => {len(_slot_filter(raw_matches, slot))}, returned={len(enriched)}, odds lookups={looked_up}"
    )
    return enriched
