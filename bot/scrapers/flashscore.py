from __future__ import annotations

from typing import Any, Dict, List, Optional

from bot.providers.free_fixtures import fetch_flashscore_day
from bot.providers.odds_scraper import fetch_flashscore_odds

from .base_scraper import BaseScraper


class FlashscoreScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__("flashscore")

    def fetch_fixtures(self, date_str: str) -> List[Dict[str, Any]]:
        return fetch_flashscore_day(date_str)

    def fetch_odds(self, home_team: str, away_team: str) -> Optional[Dict[str, Any]]:
        return fetch_flashscore_odds(home_team, away_team)
