#!/usr/bin/env python3
"""
Tipster Aggregator - Phase 2
Collect tips from all sources → save to DB
"""

import os
import sys
import re
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers.reddit_tipsters import scrape_reddit_tipsters
from bot.providers.telegram_tipsters import scrape_telegram_tipsters
from bot.providers.nemzeti_sport_scraper import scrape_nemzeti_sport
from bot.storage.tipster_tracking import (
    init_tipster_schema,
    register_tipster,
    add_tip,
    get_tipster_by_name
)


def parse_match_string(match_str: str) -> tuple:
    """
    Parse "Team A vs Team B" → (home_team, away_team)
    Handles: vs, v, -, @
    """
    
    if not match_str:
        return None, None
    
    # Try common separators
    for sep in [' vs ', ' v ', ' - ', ' @ ', ' VS ', ' V ']:
        if sep in match_str:
            parts = match_str.split(sep, 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
    
    return None, None


def estimate_match_date(tip_data: dict) -> str:
    """
    Estimate match date from tip data
    Default: today if time >= 12:00, else tomorrow
    """
    
    # If explicit date provided, use it
    if tip_data.get('match_date'):
        return tip_data['match_date']
    
    # Check current time
    now = datetime.now()
    
    # If before noon → assume matches are today/tonight
    # If after noon → assume matches are tomorrow (next day's tips)
    if now.hour < 12:
        return now.strftime("%Y-%m-%d")
    else:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")


def aggregate_all_sources():
    """
    Scrape all tipster sources and save to DB
    """
    print(f"\n{'='*60}")
    print(f"🤖 TIPSTER AGGREGATOR - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    # Initialize DB
    print("📊 Initializing database schema...")
    init_tipster_schema()
    print("✅ Database ready\n")
    
    total_tips = 0
    
    # 1. Reddit Tipsters
    print("🔴 REDDIT TIPSTERS")
    print("-" * 40)
    try:
        reddit_tips = scrape_reddit_tipsters()
        
        for tip in reddit_tips:
            tipster_name = tip.get('tipster')
            source = 'reddit'
            
            if not tipster_name:
                continue
            
            # Parse match
            match_str = tip.get('match', '')
            home_team, away_team = parse_match_string(match_str)
            
            if not home_team or not away_team:
                print(f"  ⚠️  Skipped (invalid match): {match_str}")
                continue
                
            # Register tipster if new
            tipster_id = get_tipster_by_name(tipster_name, source)
            if not tipster_id:
                tipster_id = register_tipster(tipster_name, source)
                print(f"  ✨ New tipster: {tipster_name}")
            
            # Add tip to DB
            match_date = estimate_match_date(tip)
            add_tip(
                tipster_id=tipster_id,
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                selection=tip.get('selection'),
                odds=tip.get('odds'),
                confidence=tip.get('confidence'),
                raw_text=tip.get('reasoning'),
                source_url=tip.get('url')
            )
            total_tips += 1
        
        print(f"✅ Reddit: {len(reddit_tips)} tips collected\n")
    except Exception as e:
        print(f"❌ Reddit error: {e}\n")
    
    # 2. Telegram Tipsters
    print("📱 TELEGRAM TIPSTERS")
    print("-" * 40)
    try:
        # Check if credentials available
        if not os.getenv('TELEGRAM_API_ID') or not os.getenv('TELEGRAM_API_HASH'):
            print("⚠️  Telegram credentials not set (GitHub Secrets only)")
            print("   Set locally: TELEGRAM_API_ID, TELEGRAM_API_HASH")
            telegram_tips = []
        else:
            telegram_tips = scrape_telegram_tipsters()
            
            for tip in telegram_tips:
                tipster_name = tip.get('channel', tip.get('tipster'))
                source = 'telegram'
                
                if not tipster_name:
                    continue
                
                # Parse match
                match_str = tip.get('match', '')
                home_team, away_team = parse_match_string(match_str)
                
                if not home_team or not away_team:
                    print(f"  ⚠️  Skipped (invalid match): {match_str}")
                    continue
                    
                # Register tipster if new
                tipster_id = get_tipster_by_name(tipster_name, source)
                if not tipster_id:
                    tipster_id = register_tipster(tipster_name, source)
                    print(f"  ✨ New tipster: {tipster_name}")
                
                # Add tip to DB
                match_date = estimate_match_date(tip)
                add_tip(
                    tipster_id=tipster_id,
                    match_date=match_date,
                    home_team=home_team,
                    away_team=away_team,
                    selection=tip.get('selection'),
                    odds=tip.get('odds'),
                    confidence=tip.get('confidence'),
                    raw_text=tip.get('reasoning'),
                    source_url=tip.get('message_link')
                )
                total_tips += 1
            
            print(f"✅ Telegram: {len(telegram_tips)} tips collected\n")
    except Exception as e:
        print(f"❌ Telegram error: {e}\n")
    
    # 3. Nemzeti Sport
    print("🇭🇺 NEMZETI SPORT")
    print("-" * 40)
    try:
        ns_tips = scrape_nemzeti_sport()
        
        for tip in ns_tips:
            tipster_name = tip.get('expert', tip.get('tipster', 'Nemzeti Sport'))
            source = 'nemzeti_sport'
            
            # Parse match
            match_str = tip.get('match', '')
            home_team, away_team = parse_match_string(match_str)
            
            if not home_team or not away_team:
                print(f"  ⚠️  Skipped (invalid match): {match_str}")
                continue
            
            # Register tipster if new
            tipster_id = get_tipster_by_name(tipster_name, source)
            if not tipster_id:
                tipster_id = register_tipster(tipster_name, source)
                print(f"  ✨ New tipster: {tipster_name}")
            
            # Add tip to DB
            match_date = estimate_match_date(tip)
            add_tip(
                tipster_id=tipster_id,
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                selection=tip.get('selection'),
                odds=tip.get('odds'),
                confidence=tip.get('confidence'),
                raw_text=tip.get('reasoning'),
                source_url=tip.get('article_url')
            )
            total_tips += 1
        
        print(f"✅ Nemzeti Sport: {len(ns_tips)} tips collected\n")
    except Exception as e:
        print(f"❌ Nemzeti Sport error: {e}\n")
    
    # Summary
    print(f"{'='*60}")
    print(f"📊 TOTAL: {total_tips} tips aggregated")
    print(f"{'='*60}\n")
    
    return total_tips


if __name__ == '__main__':
    aggregate_all_sources()
