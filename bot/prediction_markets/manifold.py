from __future__ import annotations

from typing import Any, Dict, List

from bot.scrapers.base_scraper import BaseScraper


class ManifoldClient:
    def __init__(self) -> None:
        self.scraper = BaseScraper("manifold")

    def fetch_football_markets(self, limit: int = 50) -> List[Dict[str, Any]]:
        data = self.scraper.request_json(
            "https://api.manifold.markets/v0/markets",
            params={"limit": str(limit)},
            cache_ttl_seconds=2 * 3600,
        )
        if not isinstance(data, list):
            return []

        out: List[Dict[str, Any]] = []
        for item in data:
            question = (item.get("question") or "")
            lower_q = question.lower()
            if "soccer" not in lower_q and "football" not in lower_q and " vs " not in lower_q:
                continue
            prob = _to_float(item.get("probability"))
            out.append(
                {
                    "platform": "manifold",
                    "outcome": question,
                    "probability": prob,
                    "market_odds": _prob_to_odds(prob),
                    "timestamp": item.get("closeTime") or item.get("createdTime") or "",
                }
            )
        return out


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _prob_to_odds(prob: float) -> float:
    if prob <= 0:
        return 0.0
    return round(1.0 / prob, 3)
