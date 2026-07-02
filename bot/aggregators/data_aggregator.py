from __future__ import annotations

from typing import Any, Dict, List

from bot.expert_sources.reddit_scraper import RedditExpertSource
from bot.expert_sources.twitter_scraper import TwitterExpertSource
from bot.prediction_markets.betfair_market import BetfairMarketClient
from bot.prediction_markets.manifold import ManifoldClient
from bot.prediction_markets.polymarket import PolymarketClient
from bot.scrapers.betfair import BetfairScraper
from bot.scrapers.espn import EspnScraper
from bot.scrapers.flashscore import FlashscoreScraper
from bot.scrapers.fotmob import FotmobScraper
from bot.scrapers.oddschecker import OddscheckerScraper
from bot.scrapers.sofascore import SofascoreScraper
from bot.storage import sqlite_store

from .cache_manager import CacheManager
from .confidence_scorer import merged_confidence
from .odds_aggregator import OddsAggregator


class DataAggregator:
    def __init__(self) -> None:
        self.cache = CacheManager()
        self.odds_aggregator = OddsAggregator()

        self.flashscore = FlashscoreScraper()
        self.sofascore = SofascoreScraper()
        self.fotmob = FotmobScraper()
        self.espn = EspnScraper()

        self.betfair = BetfairScraper()
        self.oddschecker = OddscheckerScraper()

        self.reddit = RedditExpertSource()
        self.twitter = TwitterExpertSource()

        self.polymarket = PolymarketClient()
        self.manifold = ManifoldClient()
        self.betfair_market = BetfairMarketClient()

    def merge_fixtures_from_sources(self, date_str: str) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for source_items in (
            self.flashscore.fetch_fixtures(date_str),
            self.sofascore.fetch_fixtures(date_str),
            self.fotmob.fetch_fixtures(date_str),
            self.espn.fetch_fixtures(date_str),
        ):
            for item in source_items:
                key = _fixture_key(item.get("home_team"), item.get("away_team"), date_str)
                if key not in merged:
                    merged[key] = dict(item)
                    merged[key]["sources"] = [item.get("source") or "unknown"]
                else:
                    merged[key]["sources"].append(item.get("source") or "unknown")
                    for field in ("league_name", "country_name", "kickoff_local", "fixture_id"):
                        if not merged[key].get(field) and item.get(field):
                            merged[key][field] = item.get(field)
                merged[key]["confidence"] = merged_confidence(*merged[key]["sources"])

        values = list(merged.values())
        sqlite_store.insert_data_sources(
            [
                {
                    "source_name": ",".join(v.get("sources") or []),
                    "fixture_id": str(v.get("fixture_id") or _fixture_key(v.get("home_team"), v.get("away_team"), date_str)),
                    "data_type": "fixtures",
                    "value_json": v,
                    "confidence": v.get("confidence") or 0.5,
                }
                for v in values
            ]
        )
        return values

    def enrich_fixture(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        home = fixture.get("home_team") or ""
        away = fixture.get("away_team") or ""
        if not home or not away:
            return fixture

        cache_key = f"fixture_enrich_{home}_{away}_{fixture.get('kickoff_local') or ''}".lower().replace(" ", "_")
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            merged = dict(fixture)
            merged.update(cached)
            return merged

        odds_rows = []
        flash_odds = self.flashscore.fetch_odds(home, away)
        if flash_odds:
            odds_rows.append({"source": "flashscore", **flash_odds})

        betfair_odds = self.betfair.fetch_public_odds(home, away)
        if betfair_odds:
            odds_rows.append(betfair_odds)

        oc_odds = self.oddschecker.fetch_public_odds(home, away)
        if oc_odds:
            odds_rows.append(oc_odds)

        fid = fixture.get("fixture_id")
        if fid:
            try:
                sf_odds = self.sofascore.fetch_odds(int(fid))
            except Exception:
                sf_odds = None
            if sf_odds:
                odds_rows.append({"source": "sofascore", "bookmaker": "Sofascore", "odds_1": sf_odds.get("1"), "odds_x": sf_odds.get("X"), "odds_2": sf_odds.get("2")})

        merged_odds = self.odds_aggregator.merge(odds_rows)
        if merged_odds.get("found"):
            fixture["scraper_odds"] = merged_odds
            fixture["odds"] = {
                "1": merged_odds.get("odds_1_best") or merged_odds.get("odds_1_avg"),
                "X": merged_odds.get("odds_x_best") or merged_odds.get("odds_x_avg"),
                "2": merged_odds.get("odds_2_best") or merged_odds.get("odds_2_avg"),
            }
            sqlite_store.insert_odds_history(
                fixture_id=str(fid or _fixture_key(home, away, fixture.get("kickoff_local") or "")),
                bookmaker="aggregated",
                odds_1=fixture["odds"].get("1"),
                odds_x=fixture["odds"].get("X"),
                odds_2=fixture["odds"].get("2"),
                source_rows=odds_rows,
            )

        league_name = fixture.get("league_name") or ""
        fixture["scraper_context"] = {
            "home": self.sofascore.fetch_team_context(home, league_name),
            "away": self.sofascore.fetch_team_context(away, league_name),
        }

        market_rows = []
        market_rows.extend(self.polymarket.fetch_football_markets(limit=30))
        market_rows.extend(self.manifold.fetch_football_markets(limit=30))
        market_rows.extend(self.betfair_market.fetch_market_indicator(home, away))
        if market_rows:
            sqlite_store.insert_prediction_markets(
                fixture_id=str(fid or _fixture_key(home, away, fixture.get("kickoff_local") or "")),
                rows=market_rows,
            )
            fixture["prediction_market"] = market_rows[:8]

        expert_rows = self.reddit.fetch_picks(max_items=20) + self.twitter.fetch_picks(max_items=20)
        if expert_rows:
            sqlite_store.insert_expert_picks(
                fixture_id=str(fid or _fixture_key(home, away, fixture.get("kickoff_local") or "")),
                rows=expert_rows,
            )
            fixture["expert_picks"] = expert_rows[:8]

        slim = {
            "odds": fixture.get("odds") or {},
            "scraper_odds": fixture.get("scraper_odds") or {},
            "scraper_context": fixture.get("scraper_context") or {},
            "prediction_market": fixture.get("prediction_market") or [],
            "expert_picks": fixture.get("expert_picks") or [],
        }
        self.cache.set(cache_key, slim, ttl_seconds=24 * 3600, match_start_ts=fixture.get("kickoff_local"))
        return fixture



def _fixture_key(home_team: Any, away_team: Any, date_str: Any) -> str:
    home = str(home_team or "").strip().lower()
    away = str(away_team or "").strip().lower()
    day = str(date_str or "").strip().split("T")[0]
    return f"{home}::{away}::{day}"
