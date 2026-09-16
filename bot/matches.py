"""
bot/matches.py

Napi meccslista összеállítása KIZÁRÓLAG ingyenes forrásokból:
  - SofaScore / Flashscore / LiveScore scraping (bot/providers/free_fixtures.py)
  - opcionális multi-forrás aggregátor (bot/aggregators/data_aggregator.py)
  - SofaScore ingyenes odds enrichment

Nincs API kulcs, nincs fizetős szolgáltatás.
"""

import os
import re
import datetime
from typing import Any, Dict, List, Optional

TZ = os.getenv("TIPPMIX_TIMEZONE", "Europe/Budapest")

BLOCK_COUNTRIES = [x.strip().lower() for x in (os.getenv("TIPPMIX_BLOCK_COUNTRIES") or "").split(",") if x.strip()]
BLOCK_LEAGUES = [x.strip().lower() for x in (os.getenv("TIPPMIX_BLOCK_LEAGUES") or "").split(",") if x.strip()]

MAX_FIXTURES = int(os.getenv("TIPPMIX_MAX_FIXTURES", "200"))

MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    raw = str(raw).strip()
    if raw == "":
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


MAX_DAYS_AHEAD = _get_int_env("TIPPMIX_MAX_DAYS_AHEAD", 0)
MIN_POOL = int(os.getenv("TIPPMIX_MIN_POOL", str(MIN_VIP + MIN_FREE + 12)))

ALLOW_YOUTH = (os.getenv("TIPPMIX_ALLOW_YOUTH") or "").strip() == "1"
ALLOW_FRIENDLY = (os.getenv("TIPPMIX_ALLOW_FRIENDLY") or "").strip() == "1"

TOP_LEAGUE_KEYWORDS = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "UEFA Champions League", "Champions League",
    "UEFA Europa League", "Europa League",
    "UEFA Europa Conference League", "Conference League",
    "Eredivisie", "Primeira Liga", "Scottish Premiership",
    "FA Cup", "Copa del Rey", "DFB Pokal", "Coppa Italia",
]

YOUTH_PATTERNS = [
    r"\bU\d{2}\b", r"\bU-?\d{2}\b", r"\bYouth\b", r"\bReserve\b", r"\bB Team\b",
    r"\bPrimavera\b", r"\bU23\b", r"\bU21\b", r"\bU20\b", r"\bU19\b",
]

FRIENDLY_PATTERNS = [r"friendly", r"friendlies", r"bar\u00e1ts\u00e1gos"]


# ───────────────────────────────────────────
# Helper függvények
# ───────────────────────────────────────────

def _extract_hour(iso: str) -> Optional[int]:
    if not iso or "T" not in iso:
        return None
    try:
        return int(iso.split("T")[1][:2])
    except Exception:
        return None


def _slot_filter(matches: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()
    day_start = int(os.getenv("TIPPMIX_DAY_START_HOUR", "9"))
    day_end_excl = int(os.getenv("TIPPMIX_DAY_END_HOUR_EXCL", "19"))
    eve_start = int(os.getenv("TIPPMIX_EVENING_START_HOUR", str(day_end_excl)))
    eve_end_incl = int(os.getenv("TIPPMIX_EVENING_END_HOUR_INCL", "23"))

    out: List[Dict[str, Any]] = []
    for m in matches:
        h = _extract_hour(str(m.get("kickoff_local") or ""))
        if h is None:
            out.append(m)
            continue
        if slot == "DAY":
            if day_start <= h < day_end_excl:
                out.append(m)
        else:
            if eve_start <= h <= eve_end_incl:
                out.append(m)
    return out


def _is_youth(match: Dict[str, Any]) -> bool:
    txt = f"{match.get('league_name','')} {match.get('home_team','')} {match.get('away_team','')}"
    for p in YOUTH_PATTERNS:
        if re.search(p, txt, flags=re.IGNORECASE):
            return True
    return False


def _is_friendly(match: Dict[str, Any]) -> bool:
    txt = f"{match.get('league_name','')}"
    for p in FRIENDLY_PATTERNS:
        if re.search(p, txt, flags=re.IGNORECASE):
            return True
    return False


def _is_top_match(match: Dict[str, Any]) -> bool:
    league = str(match.get("league_name") or "")
    for k in TOP_LEAGUE_KEYWORDS:
        if k.lower() in league.lower():
            return True
    return False


def _is_blocked(match: Dict[str, Any]) -> bool:
    if not BLOCK_COUNTRIES and not BLOCK_LEAGUES:
        return False
    country = (match.get("country_name") or match.get("country") or "").lower()
    league = (match.get("league_name") or match.get("league") or "").lower()
    for bc in BLOCK_COUNTRIES:
        if bc and bc in country:
            return True
    for bl in BLOCK_LEAGUES:
        if bl and bl in league:
            return True
    return False


def _rank_bucket(match: Dict[str, Any]) -> int:
    if _is_friendly(match):
        return 3
    if _is_top_match(match) and not _is_youth(match):
        return 0
    if not _is_youth(match):
        return 1
    return 2


# ───────────────────────────────────────────
# Fixture lekérés – kizárólag ingyenes scraping
# ───────────────────────────────────────────

def _fetch_fixtures_for_date(date_str: str) -> List[Dict[str, Any]]:
    from bot.providers.free_fixtures import fetch_free_fixtures

    base = fetch_free_fixtures(date_str, top_leagues_only=False)

    try:
        if (os.getenv("TIPPMIX_ENABLE_SCRAPER_PIPELINE") or "1").strip() == "1":
            from bot.aggregators.data_aggregator import DataAggregator

            merged = DataAggregator().merge_fixtures_from_sources(date_str)
            if merged:
                by_key = {
                    (str(m.get("home_team") or "").strip().lower(), str(m.get("away_team") or "").strip().lower()): m
                    for m in base
                }
                for item in merged:
                    key = (str(item.get("home_team") or "").strip().lower(), str(item.get("away_team") or "").strip().lower())
                    if key in by_key:
                        by_key[key].setdefault("extra_sources", [])
                        by_key[key]["extra_sources"] = list(
                            sorted(
                                set((by_key[key].get("extra_sources") or []) + (item.get("sources") or []))
                            )
                        )
                        by_key[key]["source_confidence"] = item.get("confidence")
                    else:
                        base.append(
                            {
                                "sport": "football",
                                "fixture_id": item.get("fixture_id") or (hash(f"{item.get('home_team')}::{item.get('away_team')}::{date_str}") & 0x7FFFFFFF),
                                "league_name": item.get("league_name") or "",
                                "country_name": item.get("country_name") or "",
                                "kickoff_local": item.get("kickoff_local") or f"{date_str}T12:00:00+00:00",
                                "home_team": item.get("home_team") or "",
                                "away_team": item.get("away_team") or "",
                                "odds": {},
                                "standings": {},
                                "injuries": [],
                                "source": "aggregated_scrapers",
                                "extra_sources": item.get("sources") or [],
                                "source_confidence": item.get("confidence"),
                            }
                        )
    except Exception:
        pass

    return base


def _fetch_fixtures_expanding(slot: str, base_date: datetime.date) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()

    def enough(fixtures: List[Dict[str, Any]]) -> bool:
        slot_fx = _slot_filter(fixtures, slot)
        tmp = slot_fx
        if BLOCK_COUNTRIES or BLOCK_LEAGUES:
            tmp = [m for m in tmp if not _is_blocked(m)]
        if not ALLOW_YOUTH:
            tmp = [m for m in tmp if not _is_youth(m)]
        if not ALLOW_FRIENDLY:
            tmp = [m for m in tmp if not _is_friendly(m)]
        return len(tmp) >= MIN_POOL

    all_fx: List[Dict[str, Any]] = []
    max_ahead = max(0, MAX_DAYS_AHEAD)

    for days_ahead in range(0, max_ahead + 1):
        day = (base_date + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        chunk = _fetch_fixtures_for_date(day)
        all_fx.extend(chunk)
        slot_fx = _slot_filter(all_fx, slot)
        print(f"[matches] fixtures: date={day} added={len(chunk)} | slot={slot} now={len(slot_fx)} total={len(all_fx)}")
        if enough(all_fx):
            return all_fx

    hard_cap = 2
    if max_ahead < hard_cap:
        for days_ahead in range(max_ahead + 1, hard_cap + 1):
            day = (base_date + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            chunk = _fetch_fixtures_for_date(day)
            all_fx.extend(chunk)
            slot_fx = _slot_filter(all_fx, slot)
            print(f"[matches] expand fallback: date={day} added={len(chunk)} | slot={slot} now={len(slot_fx)} total={len(all_fx)}")
            if enough(all_fx):
                return all_fx

    return all_fx


def fetch_matches_for_today(slot: str = "DAY", date: Optional[str] = None) -> List[Dict[str, Any]]:
    slot = (slot or "DAY").upper()

    base_date = datetime.date.today()
    if date:
        try:
            base_date = datetime.date.fromisoformat(str(date).strip())
        except Exception:
            base_date = datetime.date.today()

    fixtures = _fetch_fixtures_expanding(slot, base_date=base_date)
    print(f"[matches] fixtures expanded total -> {len(fixtures)}")

    slot_fixtures_all = _slot_filter(fixtures, slot)
    print(f"[matches] slot={slot} all -> {len(slot_fixtures_all)}")

    if not slot_fixtures_all:
        print(f"[matches] slot üres ({slot}), visszaadom a pool összes meccsét.")
        slot_fixtures_all = fixtures

    if BLOCK_COUNTRIES or BLOCK_LEAGUES:
        before = len(slot_fixtures_all)
        slot_fixtures_all = [m for m in slot_fixtures_all if not _is_blocked(m)]
        after = len(slot_fixtures_all)
        if before != after:
            print(f"[matches] blacklist filtered: {before}->{after}")

    if not ALLOW_YOUTH:
        before = len(slot_fixtures_all)
        slot_fixtures_all = [m for m in slot_fixtures_all if not _is_youth(m)]
        after = len(slot_fixtures_all)
        if before != after:
            print(f"[matches] youth filtered: {before}->{after}")

    if not ALLOW_FRIENDLY:
        before = len(slot_fixtures_all)
        slot_fixtures_all = [m for m in slot_fixtures_all if not _is_friendly(m)]
        after = len(slot_fixtures_all)
        if before != after:
            print(f"[matches] friendly filtered: {before}->{after}")

    ranked = sorted(slot_fixtures_all, key=_rank_bucket)

    slot_fixtures: List[Dict[str, Any]] = []
    for m in ranked:
        slot_fixtures.append(m)
        if len(slot_fixtures) >= MIN_POOL:
            break

    if len(slot_fixtures) < MIN_POOL and len(slot_fixtures_all) > len(slot_fixtures):
        slot_fixtures = ranked

    print(
        f"[matches] pool built: {len(slot_fixtures)} (target MIN_POOL={MIN_POOL}) | "
        f"top={sum(1 for m in slot_fixtures if _rank_bucket(m)==0)} "
        f"adult_exotic={sum(1 for m in slot_fixtures if _rank_bucket(m)==1)} "
        f"youth={sum(1 for m in slot_fixtures if _rank_bucket(m)==2)} "
        f"friendly={sum(1 for m in slot_fixtures if _rank_bucket(m)==3)}"
    )

    # SofaScore ingyenes odds enrichment
    from bot.providers.free_fixtures import fetch_sofascore_odds
    for m in slot_fixtures[:20]:
        fid = m.get("fixture_id")
        if fid and not (m.get("odds") or {}).get("1"):
            try:
                odds = fetch_sofascore_odds(int(fid))
                if odds:
                    m["odds"] = odds
                    m["odds_source"] = "sofascore"
            except Exception:
                pass

    if slot_fixtures:
        print("[matches] RAW MATCH EXAMPLE:\n", slot_fixtures[0])

    for m in slot_fixtures:
        try:
            m["bucket"] = _rank_bucket(m)
        except Exception:
            m["bucket"] = None

    # Multi-source scraper pipeline (best-effort, failure-safe)
    try:
        if (os.getenv("TIPPMIX_ENABLE_SCRAPER_PIPELINE") or "1").strip() == "1":
            from bot.aggregators.data_aggregator import DataAggregator

            max_enrich = int(os.getenv("TIPPMIX_SCRAPER_ENRICH_LIMIT", "20"))
            agg = DataAggregator()
            for idx, fixture in enumerate(slot_fixtures):
                if idx >= max_enrich:
                    break
                try:
                    slot_fixtures[idx] = agg.enrich_fixture(fixture)
                except Exception:
                    continue
    except Exception:
        pass

    return slot_fixtures
