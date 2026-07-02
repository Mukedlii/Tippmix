from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .base_scraper import BaseScraper


class BetfairScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__("betfair")

    def fetch_public_odds(self, home_team: str, away_team: str) -> Optional[Dict[str, Any]]:
        query = f"{home_team} v {away_team}"
        html = self.request_text(
            "https://www.betfair.com/sport/football",
            params={"query": query},
            cache_ttl_seconds=2 * 3600,
        )
        if not html:
            return None

        home_token = (home_team or "").lower()[:5]
        away_token = (away_team or "").lower()[:5]
        text_l = html.lower()
        if home_token and away_token and (home_token not in text_l or away_token not in text_l):
            return None

        nums = [float(x) for x in re.findall(r"\b\d{1,3}\.\d{2}\b", html)]
        if len(nums) < 3:
            return None

        return {
            "source": "betfair",
            "bookmaker": "Betfair Exchange",
            "odds_1": nums[0],
            "odds_x": nums[1],
            "odds_2": nums[2],
        }
