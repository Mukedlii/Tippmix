"""
bot/filters.py

Meccs minőség szűrő — kizárja az egzotikus/ismeretlen ligákat,
és csak magas minőségű meccseket enged át.

Integrálja a meglévő bot/providers/league_filter.py logikát
és kiegészíti odds-küszöb + meccs-fontosság ellenőrzéssel.

Használat:
    from bot.filters import apply_quality_filters
    filtered = apply_quality_filters(matches)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from bot.providers.league_filter import is_allowed_league

log = logging.getLogger(__name__)

# ── Minimális odds küszöbök (1X2) ──────────────────────────────────────────
MIN_ODDS_HOME = float(os.getenv("FILTER_MIN_ODDS_HOME", "1.10"))
MIN_ODDS_AWAY = float(os.getenv("FILTER_MIN_ODDS_AWAY", "1.10"))

# ── Liga fontossági szintek (1=legjobb, 3=közepes, None=ismeretlen/tiltott) ─
TIER1_KEYWORDS = [
    "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
    "champions league", "europa league",
    "world cup", "euro 2024", "euro 2025", "euro 2026",
    "copa america",
]

TIER2_KEYWORDS = [
    "championship", "2. bundesliga", "segunda", "serie b", "ligue 2",
    "eredivisie", "primeira liga", "liga portugal",
    "super lig", "jupiler", "pro league",
    "conference league",
    "nations league",
    "scottish premiership",
    "otp bank liga", "nb i", "nb ii", "mol liga",
]

# ── Env kapcsolók ──────────────────────────────────────────────────────────
STRICT_MODE = (os.getenv("FILTER_STRICT_MODE") or "1").strip() == "1"
ALLOW_TIER2 = (os.getenv("FILTER_ALLOW_TIER2") or "1").strip() == "1"
ALLOW_TIER3 = (os.getenv("FILTER_ALLOW_TIER3") or "1").strip() == "1"
MIN_SCORE_THRESHOLD = float(os.getenv("FILTER_MIN_SCORE", "0.0"))
TIER1_MIN_SCORE = float(os.getenv("FILTER_TIER1_MIN_SCORE", "5.0"))
TIER2_MIN_SCORE = float(os.getenv("FILTER_TIER2_MIN_SCORE", "6.0"))
TIER3_MIN_SCORE = float(os.getenv("FILTER_TIER3_MIN_SCORE", "7.0"))


def league_tier(league_name: str, country_name: str = "") -> Optional[int]:
    """
    Visszaadja a liga szintjét:
      1 = top tier (Premier League, CL, VB, stb.)
      2 = közepes tier (Championship, Eredivisie, stb.)
      3 = ismert de nem prémium
      None = tiltott / ismeretlen

    Args:
        league_name:  Liga neve
        country_name: Ország neve (opcionális)

    Returns:
        1, 2, 3, vagy None
    """
    league_lower = (league_name or "").lower().strip()
    country_lower = (country_name or "").lower().strip()

    # Először az is_allowed_league-et futtatjuk a meglévő blacklist-tel
    if not is_allowed_league(league_lower, country_lower):
        return None

    # Tier1 ellenőrzés
    if any(kw in league_lower for kw in TIER1_KEYWORDS):
        return 1

    # Tier2 ellenőrzés
    if any(kw in league_lower for kw in TIER2_KEYWORDS):
        return 2

    # Egyébként tier3 (ismert de nem prémium — pl. Czech Fortuna Liga)
    return 3


def _has_valid_odds(match: Dict[str, Any]) -> bool:
    """Ellenőrzi, hogy a meccsnek vannak-e érvényes oddszai."""
    odds = match.get("odds") or {}
    scraped = match.get("scraped_odds") or {}

    for source in (odds, scraped):
        try:
            o1 = float(source.get("1") or 0)
            o2 = float(source.get("2") or 0)
            if o1 >= MIN_ODDS_HOME and o2 >= MIN_ODDS_AWAY:
                return True
        except (TypeError, ValueError):
            continue

    return False


def _is_exotic(match: Dict[str, Any]) -> bool:
    """True ha egzotikus/tiltott meccs."""
    league = match.get("league_name") or match.get("league") or ""
    country = match.get("country_name") or match.get("country") or ""
    tier = league_tier(league, country)
    return tier is None


def apply_quality_filters(
    matches: List[Dict[str, Any]],
    allow_odds_missing: bool = True,
) -> List[Dict[str, Any]]:
    """
    Szűri a meccslistát minőség szerint:
      1. Kizárja az egzotikus / tiltott ligákat
      2. Kizárja a tier3 meccseket (ha FILTER_ALLOW_TIER3=0)
      3. Opcionálisan megköveteli az érvényes oddsot

    Args:
        matches:           Meccsek listája
        allow_odds_missing: Ha True, akkor odds nélküli meccsek is átmennek

    Returns:
        Szűrt meccsek listája, legfontosabb liga szerint rendezve
    """
    allowed: List[Dict[str, Any]] = []
    rejected_exotic: List[str] = []
    rejected_tier: List[str] = []

    for m in matches:
        league = m.get("league_name") or m.get("league") or ""
        country = m.get("country_name") or m.get("country") or ""
        tier = league_tier(league, country)

        if tier is None:
            rejected_exotic.append(f"{league} ({country})")
            continue

        if not ALLOW_TIER2 and tier >= 2:
            rejected_tier.append(f"{league} (tier{tier})")
            continue

        if not ALLOW_TIER3 and tier >= 3:
            rejected_tier.append(f"{league} (tier{tier})")
            continue

        if not allow_odds_missing and not _has_valid_odds(m):
            continue

        # Tier beírjuk a meccs adatába (scoring-hoz hasznos)
        m["league_tier"] = tier
        allowed.append(m)

    if rejected_exotic:
        unique_exotic = sorted(set(rejected_exotic))[:15]
        log.info(f"[filters] Egzotikus meccsek kizárva ({len(rejected_exotic)}): {unique_exotic}")

    if rejected_tier:
        unique_tier = sorted(set(rejected_tier))[:10]
        log.info(f"[filters] Alacsony tier meccsek kizárva ({len(rejected_tier)}): {unique_tier}")

    # Rendezés: tier1 → tier2 → tier3
    allowed.sort(key=lambda m: m.get("league_tier", 9))

    log.info(
        f"[filters] Szűrés eredménye: {len(allowed)}/{len(matches)} meccs maradt "
        f"(elutasítva: {len(rejected_exotic)} egzotikus, {len(rejected_tier)} alacsony tier)"
    )
    return allowed


def get_filter_stats(matches: List[Dict[str, Any]]) -> Dict[str, int]:
    """Visszaadja a szűrési statisztikákat (debug célra)."""
    tier1 = sum(1 for m in matches if m.get("league_tier") == 1)
    tier2 = sum(1 for m in matches if m.get("league_tier") == 2)
    tier3 = sum(1 for m in matches if m.get("league_tier") == 3)
    no_tier = sum(1 for m in matches if m.get("league_tier") is None)
    return {"tier1": tier1, "tier2": tier2, "tier3": tier3, "unknown": no_tier, "total": len(matches)}


def get_tier_min_score(league_tier: Optional[int]) -> float:
    if league_tier == 1:
        return TIER1_MIN_SCORE
    if league_tier == 2:
        return TIER2_MIN_SCORE
    return TIER3_MIN_SCORE


def apply_tiered_score_filter(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tier-függő pontszám küszöb:
      - Tier1: 5.0+
      - Tier2: 6.0+
      - Tier3: 7.0+
    """
    passed: List[Dict[str, Any]] = []
    rejected = 0

    for m in matches:
        tier = m.get("league_tier")
        threshold = get_tier_min_score(tier)
        score = float(m.get("match_score") or 0.0)
        if score >= threshold:
            passed.append(m)
        else:
            rejected += 1

    log.info(
        f"[filters] Tiered score filter: {len(passed)}/{len(matches)} meccs maradt "
        f"(kizárva: {rejected}, küszöbök: t1={TIER1_MIN_SCORE}, t2={TIER2_MIN_SCORE}, t3={TIER3_MIN_SCORE})"
    )
    return passed
