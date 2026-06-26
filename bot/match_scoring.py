"""
bot/match_scoring.py

Statisztikai meccs-értékelő modul.

Minden meccset 0-10 pontszámmal értékel a következő metrikák alapján:
  1. Liga minőség      (0-3 pont)
  2. Torna státusz     (0-2 pont)
  3. xG különbség      (0-1.5 pont) — ha elérhető
  4. Forma (utolsó 5)  (0-1.5 pont) — ha elérhető
  5. Sérülés hatás     (0-1 pont)   — ha elérhető (kevés = jobb)
  6. H2H egyértelműség (0-0.5 pont) — ha elérhető
  7. Odds minőség      (0-0.5 pont) — ha van odds

Összesen max ~10 pont.
Ajánlott küszöb: MIN_MATCH_SCORE=6.0 (env változó)

Használat:
    from bot.match_scoring import score_match, score_and_filter
    scored = score_and_filter(matches, min_score=6.0)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

MIN_MATCH_SCORE = float(os.getenv("MIN_MATCH_SCORE", "5.0"))

# ── Liga minőség pontok ────────────────────────────────────────────────────
LEAGUE_QUALITY_SCORES: Dict[int, float] = {
    1: 3.0,   # Tier1: Premier League, CL, VB stb.
    2: 2.0,   # Tier2: Championship, Eredivisie stb.
    3: 1.0,   # Tier3: ismert de nem prémium
}


def _score_league_quality(match: Dict[str, Any]) -> float:
    """Liga minőség pontszám (0-3)."""
    tier = match.get("league_tier")
    if tier is None:
        # Ha a tier nincs beállítva, próbáljuk a bucket-ből
        bucket = match.get("bucket")
        if bucket == 0:
            return 3.0
        if bucket == 1:
            return 1.5
        return 0.5
    return LEAGUE_QUALITY_SCORES.get(int(tier), 0.5)


def _score_tournament(match: Dict[str, Any]) -> float:
    """Torna státusz pontszám (0-2)."""
    priority = match.get("tournament_priority") or 0
    if priority >= 8:
        return 2.0
    if priority >= 6:
        return 1.5
    if priority >= 4:
        return 1.0
    if priority >= 1:
        return 0.5
    return 0.0


def _score_xg(match: Dict[str, Any]) -> float:
    """
    xG különbség alapú pontszám (0-1.5).

    Ha az egyik csapat xG-je lényegesen magasabb, az egyértelműbb kimenetelt jelent.
    Forrás: match.get('xg_home'), match.get('xg_away')
    """
    xg_home = match.get("xg_home")
    xg_away = match.get("xg_away")

    if xg_home is None or xg_away is None:
        return 0.5  # neutral ha nincs adat

    try:
        xg_h = float(xg_home)
        xg_a = float(xg_away)
    except (TypeError, ValueError):
        return 0.5

    diff = abs(xg_h - xg_a)

    if diff >= 1.0:
        return 1.5
    if diff >= 0.5:
        return 1.0
    if diff >= 0.2:
        return 0.7
    return 0.4  # nagyon kiegyenlített meccs


def _score_form(match: Dict[str, Any]) -> float:
    """
    Forma alapú pontszám (0-1.5).

    Forrás: match.get('home_form'), match.get('away_form')
    Forma: lista az utolsó 5 meccs eredményeiből, pl. ["W","W","D","L","W"]
    """
    home_form = match.get("home_form") or []
    away_form = match.get("away_form") or []

    if not home_form and not away_form:
        return 0.5  # neutral

    def form_score(form: List[str]) -> float:
        """5 meccs alapján forma értéke 0-1."""
        if not form:
            return 0.5
        points = 0
        total = min(len(form), 5)
        for r in form[:5]:
            r_upper = str(r).upper()
            if r_upper == "W":
                points += 3
            elif r_upper == "D":
                points += 1
        return min(1.0, points / (total * 3))

    h_score = form_score(home_form)
    a_score = form_score(away_form)

    # Egyértelmű forma különbség = jobb meccs
    diff = abs(h_score - a_score)
    base = max(h_score, a_score) * 0.5 + diff * 0.5

    return min(1.5, base * 1.5)


def _score_injuries(match: Dict[str, Any]) -> float:
    """
    Sérülés hatás pontszám (0-1).

    Kevés sérült = magasabb pont (megbízhatóbb meccs).
    Forrás: match.get('injuries') — lista
    """
    injuries = match.get("injuries") or []
    count = len(injuries)

    if count == 0:
        return 1.0
    if count <= 2:
        return 0.8
    if count <= 4:
        return 0.6
    if count <= 7:
        return 0.4
    return 0.2


def _score_h2h(match: Dict[str, Any]) -> float:
    """
    Head-to-head egyértelműség pontszám (0-0.5).

    Forrás: match.get('h2h') — dict vagy lista
    """
    h2h = match.get("h2h")
    if not h2h:
        return 0.25  # neutral

    if isinstance(h2h, dict):
        home_wins = h2h.get("home_wins", 0) or 0
        away_wins = h2h.get("away_wins", 0) or 0
        draws = h2h.get("draws", 0) or 0
        total = home_wins + away_wins + draws
    elif isinstance(h2h, list):
        total = len(h2h)
        home_wins = sum(1 for g in h2h if str(g.get("winner", "")).lower() == "home")
        away_wins = sum(1 for g in h2h if str(g.get("winner", "")).lower() == "away")
    else:
        return 0.25

    if total < 3:
        return 0.25

    dominant = max(home_wins, away_wins) / total
    if dominant >= 0.7:
        return 0.5
    if dominant >= 0.5:
        return 0.35
    return 0.2


def _score_odds_quality(match: Dict[str, Any]) -> float:
    """
    Odds minőség pontszám (0-0.5).

    Érvényes oddszok jelenléte = jobb. Extrém alacsony/magas oddszok = rosszabb.
    """
    odds = match.get("odds") or match.get("scraped_odds") or {}
    if not odds:
        return 0.1

    try:
        o1 = float(odds.get("1") or 0)
        ox = float(odds.get("X") or 0)
        o2 = float(odds.get("2") or 0)
    except (TypeError, ValueError):
        return 0.1

    if not (o1 > 1.01 and ox > 1.01 and o2 > 1.01):
        return 0.2

    # Balanced odds → jobb meccs (nem 1.05 vs 20.0)
    min_o = min(o1, o2)
    max_o = max(o1, o2)
    ratio = max_o / min_o if min_o > 0 else 99

    if ratio <= 3.0:
        return 0.5
    if ratio <= 5.0:
        return 0.35
    return 0.2


def score_match(match: Dict[str, Any]) -> float:
    """
    Kiszámolja egy meccs összesített minőségi pontszámát (0-10).

    Args:
        match: Meccs dict (league_tier, tournament_priority, xg_*, h2h, stb.)

    Returns:
        Pontszám 0.0 és 10.0 között
    """
    league_pts = _score_league_quality(match)
    tournament_pts = _score_tournament(match)
    xg_pts = _score_xg(match)
    form_pts = _score_form(match)
    injury_pts = _score_injuries(match)
    h2h_pts = _score_h2h(match)
    odds_pts = _score_odds_quality(match)

    total = league_pts + tournament_pts + xg_pts + form_pts + injury_pts + h2h_pts + odds_pts

    # Normalizálás: max elméleti = 3+2+1.5+1.5+1+0.5+0.5 = 10
    score = min(10.0, round(total, 2))
    return score


def score_and_filter(
    matches: List[Dict[str, Any]],
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Pontszámoz és szűr minden meccset.

    - Minden meccshez hozzáadja a 'match_score' mezőt
    - Visszaadja azokat, ahol match_score >= min_score
    - min_score alapértéke a MIN_MATCH_SCORE env változó (default: 5.0)

    Args:
        matches:   Meccsek listája
        min_score: Minimum pontszám (None = env változó értékét használja)

    Returns:
        Szűrt és pontszámozott meccsek listája, csökkenő sorrendben
    """
    if min_score is None:
        min_score = MIN_MATCH_SCORE

    scored: List[Tuple[float, Dict[str, Any]]] = []
    rejected = 0

    for m in matches:
        s = score_match(m)
        m["match_score"] = s

        if s >= min_score:
            scored.append((s, m))
        else:
            rejected += 1
            log.debug(
                f"[match_scoring] Kizárva (score={s:.1f} < {min_score}): "
                f"{m.get('home_team')} vs {m.get('away_team')} [{m.get('league_name')}]"
            )

    scored.sort(key=lambda x: -x[0])
    result = [m for _, m in scored]

    log.info(
        f"[match_scoring] {len(result)}/{len(matches)} meccs maradt "
        f"(elutasítva: {rejected}, min_score={min_score})"
    )
    return result


def top_matches(
    matches: List[Dict[str, Any]],
    n: int = 20,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Visszaadja a legjobb N meccset pontszám alapján.

    Args:
        matches:   Meccsek listája (nem kell előre pontszámozva lenniük)
        n:         Maximum visszaadott meccsek száma
        min_score: Minimum pontszám (None = env változó)

    Returns:
        Legjobb N meccs, csökkenő pontszám szerint
    """
    filtered = score_and_filter(matches, min_score=min_score)
    return filtered[:n]
