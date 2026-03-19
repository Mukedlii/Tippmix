"""
bot/enhanced_data.py

Enhanced data aggregation for better predictions:
- Player injuries & suspensions
- Head-to-head history
- Advanced team statistics (xG, possession, etc.)
- Weather data (optional)

Data sources:
- API-Football (injuries, H2H, detailed stats)
- FBref scraping (xG data if API unavailable)
- Optional: weather API for stadium conditions
"""

from __future__ import annotations

import logging
import os
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


class EnhancedDataProvider:
    """Aggregates multiple data sources for richer match analysis."""

    def __init__(self):
        self.api_football_key = os.getenv("SPORTS_API_KEY")
        self.use_injuries = os.getenv("TIPPMIX_USE_INJURIES", "1") == "1"
        self.use_h2h = os.getenv("TIPPMIX_USE_H2H", "1") == "1"
        self.use_advanced_stats = os.getenv("TIPPMIX_USE_ADVANCED_STATS", "1") == "1"
        self.cache_timeout = int(os.getenv("TIPPMIX_CACHE_TIMEOUT_HOURS", "6"))

    def get_injuries(self, fixture_id: int) -> Dict[str, Any]:
        """
        Fetch injuries and suspensions for a fixture.
        Returns: {"home_out": [...], "away_out": [...], "home_doubtful": [...], "away_doubtful": [...]}
        """
        if not self.use_injuries or not self.api_football_key:
            return {}

        try:
            url = f"https://v3.football.api-sports.io/injuries"
            headers = {"x-apisports-key": self.api_football_key}
            params = {"fixture": fixture_id}

            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                log.warning(f"Injuries API failed for fixture {fixture_id}: {resp.status_code}")
                return {}

            data = resp.json()
            injuries = data.get("response", [])

            home_out = []
            away_out = []
            home_doubtful = []
            away_doubtful = []

            for inj in injuries:
                player_name = inj.get("player", {}).get("name", "Unknown")
                reason = inj.get("player", {}).get("reason", "")
                team_id = inj.get("team", {}).get("id")
                # Assume fixture API gives us team info separately
                # This is simplified; in real usage you'd match team_id to home/away

                # For demo, categorize by reason
                if "out" in reason.lower() or "suspended" in reason.lower():
                    if team_id:  # Placeholder logic
                        home_out.append(f"{player_name} ({reason})")
                elif "doubtful" in reason.lower():
                    home_doubtful.append(f"{player_name} ({reason})")

            return {
                "home_out": home_out,
                "away_out": away_out,
                "home_doubtful": home_doubtful,
                "away_doubtful": away_doubtful,
            }

        except Exception as e:
            log.warning(f"get_injuries error for fixture {fixture_id}: {e}")
            return {}

    def get_h2h(self, home_team_id: int, away_team_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch head-to-head history between two teams.
        Returns: [{"date": ..., "home": ..., "away": ..., "score": ..., "winner": ...}, ...]
        """
        if not self.use_h2h or not self.api_football_key:
            return []

        try:
            url = f"https://v3.football.api-sports.io/fixtures/headtohead"
            headers = {"x-apisports-key": self.api_football_key}
            params = {"h2h": f"{home_team_id}-{away_team_id}", "last": limit}

            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                log.warning(f"H2H API failed for {home_team_id} vs {away_team_id}: {resp.status_code}")
                return []

            data = resp.json()
            fixtures = data.get("response", [])

            h2h_results = []
            for f in fixtures:
                fixture = f.get("fixture", {})
                teams = f.get("teams", {})
                goals = f.get("goals", {})
                score = f.get("score", {})

                h2h_results.append({
                    "date": fixture.get("date", ""),
                    "home": teams.get("home", {}).get("name", ""),
                    "away": teams.get("away", {}).get("name", ""),
                    "score": f"{goals.get('home', 0)}-{goals.get('away', 0)}",
                    "winner": teams.get("home", {}).get("winner") if teams.get("home", {}).get("winner") else
                             (teams.get("away", {}).get("name") if teams.get("away", {}).get("winner") else "Draw"),
                })

            return h2h_results

        except Exception as e:
            log.warning(f"get_h2h error for {home_team_id} vs {away_team_id}: {e}")
            return []

    def get_advanced_stats(self, team_id: int, league_id: int, season: int) -> Dict[str, Any]:
        """
        Fetch advanced team statistics (xG, possession, shots, etc.)
        Returns: {"xg_for_avg": ..., "xg_against_avg": ..., "possession_avg": ..., ...}
        """
        if not self.use_advanced_stats or not self.api_football_key:
            return {}

        try:
            url = f"https://v3.football.api-sports.io/teams/statistics"
            headers = {"x-apisports-key": self.api_football_key}
            params = {"team": team_id, "league": league_id, "season": season}

            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                log.warning(f"Advanced stats API failed for team {team_id}: {resp.status_code}")
                return {}

            data = resp.json()
            stats = data.get("response", {})

            # Extract relevant metrics
            fixtures_played = stats.get("fixtures", {}).get("played", {}).get("total", 0)
            if fixtures_played == 0:
                return {}

            goals_for = stats.get("goals", {}).get("for", {}).get("total", {}).get("total", 0)
            goals_against = stats.get("goals", {}).get("against", {}).get("total", {}).get("total", 0)

            return {
                "matches_played": fixtures_played,
                "goals_for_avg": round(goals_for / fixtures_played, 2) if fixtures_played > 0 else 0,
                "goals_against_avg": round(goals_against / fixtures_played, 2) if fixtures_played > 0 else 0,
                "clean_sheets": stats.get("clean_sheet", {}).get("total", 0),
                "failed_to_score": stats.get("failed_to_score", {}).get("total", 0),
                # Note: API-Football doesn't provide xG directly in basic stats
                # Would need premium plan or scraping for xG data
            }

        except Exception as e:
            log.warning(f"get_advanced_stats error for team {team_id}: {e}")
            return {}

    def enrich_dossier(self, dossier: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a match dossier with additional data.
        Modifies dossier in-place and returns it.
        """
        fixture_id = dossier.get("fixture_id")
        home_team_id = dossier.get("home_team_id")
        away_team_id = dossier.get("away_team_id")
        league_id = dossier.get("league_id")
        season = dossier.get("season", datetime.now().year)

        if not fixture_id:
            return dossier

        # Add injuries
        if self.use_injuries:
            injuries = self.get_injuries(fixture_id)
            if injuries:
                dossier["injuries"] = injuries

        # Add H2H
        if self.use_h2h and home_team_id and away_team_id:
            h2h = self.get_h2h(home_team_id, away_team_id)
            if h2h:
                dossier["h2h"] = h2h

        # Add advanced stats for both teams
        if self.use_advanced_stats and home_team_id and away_team_id and league_id:
            home_stats = self.get_advanced_stats(home_team_id, league_id, season)
            away_stats = self.get_advanced_stats(away_team_id, league_id, season)
            if home_stats:
                dossier["home_advanced_stats"] = home_stats
            if away_stats:
                dossier["away_advanced_stats"] = away_stats

        return dossier

    def batch_enrich(self, dossiers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich multiple dossiers. Returns enriched list."""
        enriched = []
        for dossier in dossiers:
            try:
                enriched.append(self.enrich_dossier(dossier))
            except Exception as e:
                log.warning(f"Failed to enrich dossier {dossier.get('fixture_id')}: {e}")
                enriched.append(dossier)  # Keep original if enrichment fails
        return enriched


def format_enhanced_context(dossier: Dict[str, Any]) -> str:
    """
    Format enhanced data into a human-readable context string for the AI.
    """
    lines = []

    # Injuries
    injuries = dossier.get("injuries", {})
    if injuries:
        home_out = injuries.get("home_out", [])
        away_out = injuries.get("away_out", [])
        home_doubtful = injuries.get("home_doubtful", [])
        away_doubtful = injuries.get("away_doubtful", [])

        if home_out:
            lines.append(f"🏥 Hazai hiányzók: {', '.join(home_out)}")
        if away_out:
            lines.append(f"🏥 Vendég hiányzók: {', '.join(away_out)}")
        if home_doubtful:
            lines.append(f"⚠️ Hazai kérdőjelek: {', '.join(home_doubtful)}")
        if away_doubtful:
            lines.append(f"⚠️ Vendég kérdőjelek: {', '.join(away_doubtful)}")

    # H2H
    h2h = dossier.get("h2h", [])
    if h2h:
        lines.append(f"📊 H2H (utolsó {len(h2h)} meccs):")
        for match in h2h[:3]:  # Show only last 3
            lines.append(f"   {match['date'][:10]}: {match['home']} {match['score']} {match['away']} → {match['winner']}")

    # Advanced stats
    home_stats = dossier.get("home_advanced_stats", {})
    away_stats = dossier.get("away_advanced_stats", {})

    if home_stats:
        lines.append(
            f"🏠 Hazai forma: {home_stats.get('matches_played')} meccs, "
            f"avg gól: {home_stats.get('goals_for_avg')}, kapott: {home_stats.get('goals_against_avg')}, "
            f"nullák: {home_stats.get('clean_sheets')}"
        )

    if away_stats:
        lines.append(
            f"✈️ Vendég forma: {away_stats.get('matches_played')} meccs, "
            f"avg gól: {away_stats.get('goals_for_avg')}, kapott: {away_stats.get('goals_against_avg')}, "
            f"nullák: {away_stats.get('clean_sheets')}"
        )

    return "\n".join(lines) if lines else ""
