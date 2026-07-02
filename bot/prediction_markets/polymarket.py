from __future__ import annotations

from typing import Any, Dict, List

from bot.scrapers.base_scraper import BaseScraper


class PolymarketClient:
    def __init__(self) -> None:
        self.scraper = BaseScraper("polymarket")

    def fetch_football_markets(self, limit: int = 50) -> List[Dict[str, Any]]:
        data = self.scraper.request_json(
            "https://gamma-api.polymarket.com/markets",
            params={"active": "true", "limit": str(limit)},
            cache_ttl_seconds=2 * 3600,
        )
        if not isinstance(data, list):
            return []

        out: List[Dict[str, Any]] = []
        for item in data:
            title = (item.get("question") or "").lower()
            if "soccer" not in title and "football" not in title and " vs " not in title:
                continue
            out.append(
                {
                    "platform": "polymarket",
                    "outcome": item.get("question") or "",
                    "probability": _to_float(item.get("probability")),
                    "market_odds": _prob_to_odds(_to_float(item.get("probability"))),
                    "timestamp": item.get("endDate") or item.get("createdAt") or "",
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
