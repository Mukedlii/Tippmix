"""
bot/tournament_detector.py

Nagy tornák / VB / EB felismerő modul.

Feladat:
  - Felismeri a nagy tornákat (VB, Euro, CL, EL stb.)
  - Alacsonyabb szűrési küszöböt alkalmaz rájuk (= több meccs kiválasztva)
  - Prioritást ad nekik az AI kontextusban és a VIP üzenetekben
  - Visszaad egy "tournament_label" mezőt a meccs dict-be

Használat:
    from bot.tournament_detector import enrich_with_tournament_info, is_major_tournament
    matches = enrich_with_tournament_info(matches)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ── Torna definíciók ────────────────────────────────────────────────────────
# (minta, display neve, prioritás 1-10, threshold csökkentés %)
TOURNAMENTS: List[Dict[str, Any]] = [
    # Világbajnokság
    {
        "patterns": [r"\bworld cup\b", r"\bweltmeisterschaft\b", r"\bfifa wc\b",
                     r"\bvb\b", r"\bvilágbajnokság\b", r"\bworld championship\b"],
        "label": "🌍 VB",
        "priority": 10,
        "threshold_factor": 0.7,
    },
    # Európa-bajnokság
    {
        "patterns": [r"\beuro\s*\d{4}\b", r"\beuropean championship\b",
                     r"\beb\b", r"\beurópa-bajnokság\b"],
        "label": "🇪🇺 EB",
        "priority": 9,
        "threshold_factor": 0.7,
    },
    # Copa America
    {
        "patterns": [r"\bcopa america\b", r"\bcopa am[eé]rica\b"],
        "label": "🌎 Copa America",
        "priority": 8,
        "threshold_factor": 0.75,
    },
    # Champions League
    {
        "patterns": [r"\bchampions league\b", r"\bucl\b", r"\buefa cl\b",
                     r"\bbajnokok ligája\b"],
        "label": "⭐ BL",
        "priority": 8,
        "threshold_factor": 0.75,
    },
    # Europa League
    {
        "patterns": [r"\beuropa league\b", r"\buel\b", r"\buefa el\b",
                     r"\beurópai liga\b"],
        "label": "🟠 EL",
        "priority": 7,
        "threshold_factor": 0.8,
    },
    # Conference League
    {
        "patterns": [r"\bconference league\b", r"\becl\b", r"\buefa conference\b"],
        "label": "🔵 Konferencia liga",
        "priority": 6,
        "threshold_factor": 0.85,
    },
    # Nations League
    {
        "patterns": [r"\bnations league\b", r"\bnl\b", r"\bnaciones\b"],
        "label": "🏳️ Nations League",
        "priority": 5,
        "threshold_factor": 0.85,
    },
    # FA Cup / Copa del Rey / DFB Pokal / Coppa Italia
    {
        "patterns": [r"\bfa cup\b", r"\bcopa del rey\b", r"\bdfb.?pokal\b",
                     r"\bcoppa italia\b", r"\bcoupe de france\b"],
        "label": "🏆 Nemzeti kupa",
        "priority": 5,
        "threshold_factor": 0.85,
    },
    # Major derbik (regex alapon nem detektálható könnyen, de
    # a meta-mezőkből (is_derby) kiolvasható ha van)
]


def _detect_tournament(league_name: str) -> Optional[Dict[str, Any]]:
    """
    Megkeresi a ligához tartozó tornát.

    Returns:
        A talált torna dict vagy None
    """
    league_lower = (league_name or "").lower().strip()
    for t in TOURNAMENTS:
        for pattern in t["patterns"]:
            if re.search(pattern, league_lower, flags=re.IGNORECASE):
                return t
    return None


def is_major_tournament(league_name: str) -> bool:
    """True ha a liga egy nagy torna (VB, EB, CL, EL stb.)."""
    return _detect_tournament(league_name) is not None


def get_tournament_priority(league_name: str) -> int:
    """
    Visszaadja a torna prioritását (0-10).
    0 = nem torna, 10 = VB/EB
    """
    t = _detect_tournament(league_name)
    return t["priority"] if t else 0


def get_threshold_factor(league_name: str) -> float:
    """
    Visszaadja a szűrési küszöb faktort (0.7-1.0).
    VB/EB → 0.7 (engedékenyebb, több meccs)
    Nem torna → 1.0 (normál)
    """
    t = _detect_tournament(league_name)
    return t["threshold_factor"] if t else 1.0


def get_tournament_label(league_name: str) -> str:
    """Visszaadja a torna display labelét, vagy üres string."""
    t = _detect_tournament(league_name)
    return t["label"] if t else ""


def enrich_with_tournament_info(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Minden meccshez hozzáadja a torna információkat:
      - is_tournament (bool)
      - tournament_label (str)
      - tournament_priority (int 0-10)
      - threshold_factor (float)

    Args:
        matches: Meccsek listája

    Returns:
        Ugyanaz a lista, gazdagítva
    """
    tournament_count = 0

    for m in matches:
        league = m.get("league_name") or m.get("league") or ""
        t = _detect_tournament(league)

        if t:
            m["is_tournament"] = True
            m["tournament_label"] = t["label"]
            m["tournament_priority"] = t["priority"]
            m["threshold_factor"] = t["threshold_factor"]
            tournament_count += 1
        else:
            m.setdefault("is_tournament", False)
            m.setdefault("tournament_label", "")
            m.setdefault("tournament_priority", 0)
            m.setdefault("threshold_factor", 1.0)

    if tournament_count:
        import logging
        logging.getLogger(__name__).info(
            f"[tournament_detector] {tournament_count}/{len(matches)} meccs torna meccs"
        )

    return matches


def sort_by_tournament_priority(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rendezi a meccseket torna prioritás alapján (VB meccsek előre).
    Egyenlő prioritásnál az eredeti sorrend megmarad.
    """
    return sorted(
        matches,
        key=lambda m: -(m.get("tournament_priority") or 0),
    )
