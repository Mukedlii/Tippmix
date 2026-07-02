from __future__ import annotations

from typing import Any, Dict, List, Optional

from bot.providers.free_fixtures import fetch_sofascore_day, fetch_sofascore_odds
from bot.providers.web_context import get_transfermarkt_injuries, get_understat_team_xg

from .base_scraper import BaseScraper


class SofascoreScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__("sofascore")

    def fetch_fixtures(self, date_str: str) -> List[Dict[str, Any]]:
        return fetch_sofascore_day(date_str)

    def fetch_odds(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        return fetch_sofascore_odds(fixture_id)

    def fetch_team_context(self, team_name: str, league_name: str) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {}
        xg = get_understat_team_xg(team_name, league_name)
        if xg:
            ctx["xg"] = xg
        injuries = get_transfermarkt_injuries(team_name)
        if injuries:
            ctx["injuries"] = injuries
        return ctx
