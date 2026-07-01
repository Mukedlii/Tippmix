from __future__ import annotations

from typing import Any, Dict, List

from bot.scrapers.betfair import BetfairScraper


class BetfairMarketClient:
    def __init__(self) -> None:
        self.scraper = BetfairScraper()

    def fetch_market_indicator(self, home_team: str, away_team: str) -> List[Dict[str, Any]]:
        odds = self.scraper.fetch_public_odds(home_team, away_team)
        if not odds:
            return []

        o1 = _to_float(odds.get("odds_1"))
        ox = _to_float(odds.get("odds_x"))
        o2 = _to_float(odds.get("odds_2"))
        return [
            {
                "platform": "betfair",
                "outcome": f"{home_team} vs {away_team}",
                "probability": _implied_probability(o1, ox, o2),
                "market_odds": max(o1, o2, ox),
                "timestamp": "",
            }
        ]


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _implied_probability(o1: float, ox: float, o2: float) -> float:
    probs = [1 / x for x in (o1, ox, o2) if x > 1]
    return round(max(probs), 4) if probs else 0.0
