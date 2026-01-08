from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

PickMarket = Literal["1X2", "BTTS", "OU25", "AH"]


@dataclass
class TipPick:
    fixture_id: int
    home_team: str
    away_team: str
    league_name: str
    kickoff_local: str

    market: PickMarket
    pick: str                 # pl. "1" / "X" / "2" / "BTTS:Yes" / "O2.5" / "AH:-0.25 Home"
    odds: Optional[float]     # ha van

    confidence: float         # 0.0 - 1.0
    risk: Literal["low", "medium", "high"]
    reasoning: str            # rövid indok


@dataclass
class GrokReviewItem:
    fixture_id: int
    verdict: Literal["approve", "reject", "replace"]
    replacement_pick: Optional[str] = None
    replacement_market: Optional[PickMarket] = None
    replacement_odds: Optional[float] = None
    notes: str = ""
    confidence: float = 0.5


@dataclass
class GrokReview:
    summary: str
    items: list[GrokReviewItem]
    extra_suggestions: list[dict[str, Any]]  # opcionális alternatívák
