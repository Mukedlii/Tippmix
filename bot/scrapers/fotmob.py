from __future__ import annotations

from typing import Any, Dict, List

from .base_scraper import BaseScraper


class FotmobScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__("fotmob")

    def fetch_fixtures(self, date_str: str) -> List[Dict[str, Any]]:
        data = self.request_json("https://www.fotmob.com/api/matches", params={"date": date_str}, cache_ttl_seconds=3 * 3600)
        if not isinstance(data, dict):
            return []

        items: List[Dict[str, Any]] = []
        for league in data.get("leagues", []) or []:
            lname = league.get("name") or ""
            cname = (league.get("ccode") or "").upper()
            for match in league.get("matches", []) or []:
                home = ((match.get("home") or {}).get("name") or "").strip()
                away = ((match.get("away") or {}).get("name") or "").strip()
                if not home or not away:
                    continue
                items.append(
                    {
                        "fixture_id": match.get("id"),
                        "league_name": lname,
                        "country_name": cname,
                        "home_team": home,
                        "away_team": away,
                        "kickoff_local": match.get("status", {}).get("utcTime") or "",
                        "source": "fotmob",
                    }
                )
        return items
