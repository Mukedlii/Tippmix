from __future__ import annotations

from typing import Dict


SOURCE_WEIGHTS: Dict[str, float] = {
    "flashscore": 0.95,
    "sofascore": 0.94,
    "fotmob": 0.9,
    "espn": 0.88,
    "betfair": 0.85,
    "oddschecker": 0.82,
    "reddit": 0.7,
    "twitter": 0.6,
    "polymarket": 0.55,
    "manifold": 0.5,
}


def source_confidence(source: str) -> float:
    return SOURCE_WEIGHTS.get((source or "").strip().lower(), 0.5)


def merged_confidence(*sources: str) -> float:
    vals = [source_confidence(s) for s in sources if s]
    if not vals:
        return 0.5
    return round(sum(vals) / len(vals), 3)
