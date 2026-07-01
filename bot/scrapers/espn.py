from __future__ import annotations

from typing import Any, Dict, List

from .base_scraper import BaseScraper


class EspnScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__("espn")

    def fetch_fixtures(self, date_str: str) -> List[Dict[str, Any]]:
        ymd = date_str.replace("-", "")
        data = self.request_json(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard",
            params={"dates": ymd},
            cache_ttl_seconds=3 * 3600,
        )
        if not isinstance(data, dict):
            return []

        out: List[Dict[str, Any]] = []
        for ev in data.get("events", []) or []:
            comps = ev.get("competitions") or []
            if not comps:
                continue
            comp = comps[0] or {}
            teams = comp.get("competitors") or []
            home = away = ""
            for team in teams:
                side = (team.get("homeAway") or "").lower()
                name = (team.get("team") or {}).get("displayName") or ""
                if side == "home":
                    home = name
                elif side == "away":
                    away = name
            if not home or not away:
                continue

            league_name = ((ev.get("league") or {}).get("name") or "")
            out.append(
                {
                    "fixture_id": ev.get("id"),
                    "league_name": league_name,
                    "country_name": "",
                    "home_team": home,
                    "away_team": away,
                    "kickoff_local": ev.get("date") or "",
                    "source": "espn",
                }
            )
        return out
