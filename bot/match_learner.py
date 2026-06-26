"""
bot/match_learner.py

Történeti tanulás modul — kiterjeszti a bot/self_learning.py funkcionalitást.

Feladata:
  1. Nyomon követi: Melyik meccseket választottuk ki, milyen oddsot jósoltunk, mi lett
  2. Kiszámítja: Várható vs tényleges odds pontosság
  3. Következő futásra: Történeti minták alapján javítja a meccs-pontszámozást
  4. Per-liga scoring: Egyes ligák "megbízhatósági mutatójának" számítása

Hogyan különbözik a self_learning.py-tól:
  - Meccs-szintű scoring javítás (nem csak liga-szintű)
  - Odds pontosság mérése
  - Pontszám módosítás visszacsatolás alapján

Használat:
    from bot.match_learner import apply_learning_scores, build_enhanced_learning_context
    matches = apply_learning_scores(matches)
    context = build_enhanced_learning_context(days=30)
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Importáljuk a meglévő self_learning modult
try:
    from bot.self_learning import fetch_resolved_bets, evaluate_bet, compute_stats
    _self_learning_available = True
except ImportError:
    _self_learning_available = False
    log.warning("[match_learner] bot.self_learning nem elérhető, csökkentett módban fut")


def _compute_league_reliability(days: int = 60) -> Dict[str, float]:
    """
    Liga megbízhatósági faktorok számítása a múltbeli tippek alapján.

    Returns:
        Dict(liga_neve → megbízhatósági faktor 0.5-1.5)
        1.0 = átlagos, >1.0 = jobb mint átlag, <1.0 = rosszabb
    """
    if not _self_learning_available:
        return {}

    try:
        bets = fetch_resolved_bets(days=days)
    except Exception as e:
        log.warning(f"[match_learner] fetch_resolved_bets hiba: {e}")
        return {}

    if not bets:
        return {}

    # Per-liga statisztika
    league_data: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "won": 0})

    for bet in bets:
        result = evaluate_bet(bet)
        if result is None:
            continue
        league = (bet.get("league_name") or "ismeretlen").strip()
        league_data[league]["total"] += 1
        if result:
            league_data[league]["won"] += 1

    # Teljes hitrate
    total_all = sum(d["total"] for d in league_data.values())
    won_all = sum(d["won"] for d in league_data.values())
    overall_hr = (won_all / total_all) if total_all > 0 else 0.5

    # Liga faktorok
    factors: Dict[str, float] = {}
    for league, data in league_data.items():
        if data["total"] < 5:
            continue  # nem elég adat
        hr = data["won"] / data["total"]
        # Faktor: liga hitrate / összesített hitrate
        # Clamp: 0.5 - 1.5
        factor = min(1.5, max(0.5, hr / max(overall_hr, 0.01)))
        factors[league] = round(factor, 3)

    return factors


def _compute_odds_accuracy(days: int = 60) -> Dict[str, Any]:
    """
    Odds pontossági statisztikák számítása.

    Returns:
        Dict az odds pontossági adatokkal
    """
    if not _self_learning_available:
        return {}

    try:
        bets = fetch_resolved_bets(days=days)
    except Exception as e:
        log.warning(f"[match_learner] odds accuracy hiba: {e}")
        return {}

    if not bets:
        return {}

    accurate = 0
    total = 0
    over_estimated = 0  # odds túl magas → elvesztett tipp

    for bet in bets:
        odds_pick = bet.get("odds_pick")
        if not odds_pick:
            continue
        try:
            o = float(odds_pick)
        except (TypeError, ValueError):
            continue

        result = evaluate_bet(bet)
        if result is None:
            continue

        total += 1
        if result:
            accurate += 1
        else:
            if o > 2.0:
                over_estimated += 1

    if total == 0:
        return {}

    return {
        "total": total,
        "accurate": accurate,
        "accuracy_pct": round(accurate / total * 100, 1),
        "over_estimated": over_estimated,
        "over_estimated_pct": round(over_estimated / total * 100, 1),
    }


def apply_learning_scores(
    matches: List[Dict[str, Any]],
    days: int = 60,
) -> List[Dict[str, Any]]:
    """
    Alkalmazza a tanulási faktorokat a meccsek pontszámára.

    Ha egy ligában jó múltbeli teljesítmény volt → növeli a pontszámot
    Ha egy ligában gyenge múltbeli teljesítmény volt → csökkenti a pontszámot

    Args:
        matches: Meccsek listája (match_score mezővel)
        days:    Hány napra visszamenőleg tanuljon

    Returns:
        Módosított pontszámú meccsek listája
    """
    factors = _compute_league_reliability(days=days)
    if not factors:
        return matches  # Nincs elég adat, változatlan visszaadás

    adjusted = 0
    for m in matches:
        league = (m.get("league_name") or "").strip()
        factor = factors.get(league)

        if factor is not None and "match_score" in m:
            original = m["match_score"]
            adjusted_score = min(10.0, round(original * factor, 2))
            m["match_score"] = adjusted_score
            m["learning_factor"] = factor

            if factor != 1.0:
                adjusted += 1
                log.debug(
                    f"[match_learner] {league}: {original:.2f} → {adjusted_score:.2f} "
                    f"(faktor={factor})"
                )

    if adjusted:
        log.info(f"[match_learner] {adjusted}/{len(matches)} meccs pontszáma módosítva tanulás alapján")

    return matches


def get_avoid_leagues(
    days: int = 60,
    max_hitrate: float = 0.45,
    min_samples: int = 5,
) -> List[str]:
    """
    Visszaadja azokat a ligákat ahol a hitrate nagyon alacsony.

    Args:
        days:        Visszatekintési időszak napokban
        max_hitrate: Ha hitrate <= ez, a liga kerülendő
        min_samples: Minimum tippek száma (kevesebb → nem értékeljük)

    Returns:
        Kerülendő ligák listája
    """
    if not _self_learning_available:
        return []

    try:
        bets = fetch_resolved_bets(days=days)
    except Exception as e:
        log.warning(f"[match_learner] get_avoid_leagues hiba: {e}")
        return []

    if not bets:
        return []

    league_data: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "won": 0})

    for bet in bets:
        result = evaluate_bet(bet)
        if result is None:
            continue
        league = (bet.get("league_name") or "ismeretlen").strip()
        league_data[league]["total"] += 1
        if result:
            league_data[league]["won"] += 1

    avoid = []
    for league, data in league_data.items():
        if data["total"] < min_samples:
            continue
        hr = data["won"] / data["total"]
        if hr <= max_hitrate:
            avoid.append(league)

    return avoid


def build_enhanced_learning_context(days: int = 30) -> str:
    """
    Kibővített tanulás kontextus az AI prompthoz.

    Tartalmaz:
      - Alap teljesítmény statisztikák (from self_learning)
      - Odds pontossági visszacsatolás
      - Per-liga megbízhatósági értékelés

    Args:
        days: Hány napra visszamenőleg

    Returns:
        Kontextus szöveg string
    """
    # Alap tanulság (meglévő modul)
    base_context = ""
    if _self_learning_available:
        try:
            from bot.self_learning import build_learning_context
            base_context = build_learning_context(days=days)
        except Exception as e:
            log.warning(f"[match_learner] base learning context hiba: {e}")

    lines: List[str] = []

    if base_context:
        lines.append(base_context)

    # Odds pontossági visszacsatolás
    odds_acc = _compute_odds_accuracy(days=days)
    if odds_acc and odds_acc.get("total", 0) >= 5:
        lines.append("=== ODDS PONTOSSÁGI VISSZACSATOLÁS ===")
        lines.append(f"Összes odds-alapú tipp: {odds_acc['total']}")
        lines.append(f"Pontosság: {odds_acc['accuracy_pct']}%")
        if odds_acc.get("over_estimated_pct", 0) > 20:
            lines.append(
                f"⚠️ Túlbecsülés arány: {odds_acc['over_estimated_pct']}% "
                "(magas oddszokra veszett tippek aránya magas → óvatosabb odds választás)"
            )
        lines.append("")

    # Liga megbízhatósági faktorok
    factors = _compute_league_reliability(days=days)
    if factors:
        good = [(lg, f) for lg, f in factors.items() if f >= 1.2]
        bad = [(lg, f) for lg, f in factors.items() if f <= 0.7]

        if good:
            good.sort(key=lambda x: -x[1])
            lines.append("✅ Megbízható ligák (történeti adat alapján):")
            for lg, f in good[:3]:
                lines.append(f"  - {lg}: megbízhatósági faktor {f:.2f}x")
            lines.append("")

        if bad:
            bad.sort(key=lambda x: x[1])
            lines.append("⚠️ Kockázatos ligák (gyenge múltbeli teljesítmény):")
            for lg, f in bad[:3]:
                lines.append(f"  - {lg}: megbízhatósági faktor {f:.2f}x ← KÖRÜLTEKINTŐEN")
            lines.append("")

    if lines:
        lines.append(
            "INSTRUKCIÓ: A fenti tanulságok alapján ERŐSEN PREFERÁLD a megbízható "
            "ligákat és kerüld a kockázatosakat. "
            "Ha az odds nem egyezik a statisztikai metrikákkal, UTASÍTSD EL a meccset."
        )

    return "\n".join(lines)
