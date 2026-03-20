#!/usr/bin/env python3
"""
Historical data backfill script

Downloads finished matches from football-data.org for top leagues
and populates the results table for better Poisson predictions.

Usage:
  python scripts/backfill_historical_data.py --season 2023 --competitions PL,PD,SA
  python scripts/backfill_historical_data.py --all  # all free tier leagues, last 3 seasons
"""

import argparse
import os
import sys
import time
from datetime import datetime

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers import football_data
from bot.storage.sqlite_store import upsert_result


def backfill_competition(comp_code: str, season: int):
    """Download and store historical matches for a competition"""
    comp_name = football_data.FREE_TIER_COMPETITIONS.get(comp_code, comp_code)
    
    print(f"\nđź“Ą Fetching {comp_name} ({comp_code}) - Season {season}/{season+1}...")
    
    try:
        data = football_data.get_matches_for_comp(comp_code, season=season, status="FINISHED")
    except Exception as e:
        print(f"âťŚ Error fetching {comp_code}: {e}")
        return 0
    
    matches = data.get("matches", [])
    if not matches:
        print(f"   No finished matches found.")
        return 0
    
    print(f"   Found {len(matches)} finished matches")
    
    stored = 0
    for match in matches:
        try:
            fixture_id = match.get("id")
            if not fixture_id:
                continue
            
            score = match.get("score", {})
            full_time = score.get("fullTime", {})
            home_goals = full_time.get("home")
            away_goals = full_time.get("away")
            
            if home_goals is None or away_goals is None:
                continue  # Match finished but no score (postponed/cancelled)
            
            # Determine result
            if home_goals > away_goals:
                result_1x2 = "1"
            elif home_goals < away_goals:
                result_1x2 = "2"
            else:
                result_1x2 = "X"
            
            # Extract team/league IDs
            home_team = match.get("homeTeam", {})
            away_team = match.get("awayTeam", {})
            competition = match.get("competition", {})
            
            home_team_id = home_team.get("id")
            away_team_id = away_team.get("id")
            league_id = competition.get("id")
            
            # Season year
            season_obj = match.get("season", {})
            season_year = season_obj.get("startDate", "")[:4] if season_obj.get("startDate") else None
            
            # Store in database
            upsert_result(
                fixture_id=fixture_id,
                final_score=f"{home_goals}-{away_goals}",
                result_1x2=result_1x2,
                status="FT",
                home_goals=home_goals,
                away_goals=away_goals,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                league_id=league_id,
                season=int(season_year) if season_year and season_year.isdigit() else None,
                raw_json=match
            )
            
            stored += 1
            
        except Exception as e:
            print(f"   âš ď¸Ź  Error storing match {match.get('id')}: {e}")
            continue
    
    print(f"   âś… Stored {stored}/{len(matches)} matches")
    return stored


def main():
    parser = argparse.ArgumentParser(description="Backfill historical match data")
    parser.add_argument("--season", type=int, help="Season year (e.g., 2023 for 2023/24)")
    parser.add_argument("--competitions", type=str, help="Comma-separated comp codes (e.g., PL,PD,SA)")
    parser.add_argument("--all", action="store_true", help="Backfill all free tier competitions, last 3 seasons")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't store")
    
    args = parser.parse_args()
    
    # Check API key
    if not os.getenv("FOOTBALLDATA_API_KEY") and not os.getenv("FOOTBALL_DATA_TOKEN"):
        print("âťŚ Error: FOOTBALLDATA_API_KEY or FOOTBALL_DATA_TOKEN not set")
        sys.exit(1)
    
    if args.all:
        # Top 5 leagues + CL/EL, last 3 seasons
        competitions = ["PL", "PD", "SA", "BL1", "FL1", "CL", "EL"]
        current_year = datetime.now().year
        seasons = [current_year - 3, current_year - 2, current_year - 1]
    else:
        if not args.season or not args.competitions:
            print("âťŚ Error: --season and --competitions required (or use --all)")
            parser.print_help()
            sys.exit(1)
        
        competitions = [c.strip().upper() for c in args.competitions.split(",")]
        seasons = [args.season]
    
    print("="*60)
    print("đźŹźď¸Ź  TIPPMIX HISTORICAL DATA BACKFILL")
    print("="*60)
    print(f"Competitions: {', '.join(competitions)}")
    print(f"Seasons: {', '.join(str(s) for s in seasons)}")
    print(f"Dry run: {args.dry_run}")
    print("="*60)
    
    total_stored = 0
    
    for comp in competitions:
        for season in seasons:
            count = backfill_competition(comp, season)
            total_stored += count
            
            # Rate limit: 10 req/min on free tier
            time.sleep(7)  # ~8-9 req/min to be safe
    
    print("\n" + "="*60)
    print(f"âś… DONE: Stored {total_stored} total matches")
    print("="*60)
    
    if total_stored > 0:
        print("\nđź’ˇ Next steps:")
        print("   1. Check: python -m bot.storage.poisson_stats")
        print("   2. Generate tips to see improved accuracy")


if __name__ == "__main__":
    main()

