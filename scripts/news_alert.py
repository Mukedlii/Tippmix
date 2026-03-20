#!/usr/bin/env python3
"""
News alert for today's matches

Fetches breaking news and matches it against today's Tippmix picks
Sends Telegram alert if relevant news found

Usage:
  python scripts/news_alert.py
"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers import news_rss
from bot.tips_logger import read_tips
import requests


def send_telegram_alert(message: str):
    """Send Telegram message"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")  # or PUBLIC
    
    if not token or not chat_id:
        print("Telegram credentials not set, skipping alert")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("Telegram alert sent")
        else:
            print(f"Telegram error: {resp.status_code}")
    except Exception as e:
        print(f"Telegram send failed: {e}")


def match_news_to_picks(news_items, picks):
    """
    Match breaking news to today's picks
    
    Returns:
        List of (news_item, matched_picks)
    """
    matches = []
    
    for news in news_items:
        news_teams = set([t.lower() for t in news.get("mentioned_teams", [])])
        news_title = news.get("title", "").lower()
        
        matched_picks = []
        
        for pick in picks:
            pick_home = (pick.get("home_team", "") or "").lower()
            pick_away = (pick.get("away_team", "") or "").lower()
            
            # Check if any mentioned team matches pick teams
            for team in news_teams:
                if team in pick_home or team in pick_away:
                    matched_picks.append(pick)
                    break
            
            # Also check if team names appear in news title
            if pick_home and pick_home in news_title:
                if pick not in matched_picks:
                    matched_picks.append(pick)
            if pick_away and pick_away in news_title:
                if pick not in matched_picks:
                    matched_picks.append(pick)
        
        if matched_picks:
            matches.append((news, matched_picks))
    
    return matches


def format_alert_message(matches):
    """Format matched news + picks for Telegram"""
    if not matches:
        return None
    
    lines = ["BREAKING NEWS ALERT", ""]
    
    for news, picks in matches:
        title = news.get("title", "No title")
        source = news.get("source", "").upper()
        link = news.get("link", "")
        
        lines.append(f"{source}: {title}")
        lines.append(f"{link}")
        lines.append("")
        lines.append("AFFECTED PICKS:")
        
        for pick in picks:
            match_str = f"{pick.get('home_team', '?')} vs {pick.get('away_team', '?')}"
            tip = pick.get('tip', '?')
            lines.append(f"  - {match_str} (Tipp: {tip})")
        
        lines.append("")
        lines.append("-" * 40)
        lines.append("")
    
    return "\n".join(lines)


def main():
    print("="*50)
    print("NEWS ALERT - Checking breaking news...")
    print("="*50)
    
    # 1. Get breaking news (last 6 hours)
    print("\nFetching RSS feeds...")
    news = news_rss.get_breaking_news(max_age_hours=6, min_relevance=1)
    print(f"Found {len(news)} relevant news items")
    
    # 2. Get today's picks
    print("\nLoading today's picks...")
    run_date = datetime.now().strftime("%Y-%m-%d")
    
    all_picks = []
    
    # Try to load from tips log
    try:
        tips = read_tips(run_date=run_date)
        all_picks.extend(tips.get("vip", []))
        all_picks.extend(tips.get("public", []))
    except Exception as e:
        print(f"Could not load tips: {e}")
    
    # Try to load from JSON files
    for json_file in ["vip_bets_day.json", "public_bets_day.json"]:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_picks.extend(data)
        except Exception:
            pass
    
    print(f"Loaded {len(all_picks)} picks for {run_date}")
    
    if not all_picks:
        print("No picks found for today, exiting")
        return
    
    # 3. Match news to picks
    print("\nMatching news to picks...")
    matches = match_news_to_picks(news, all_picks)
    
    if not matches:
        print("No relevant news for today's picks")
        return
    
    print(f"\nFOUND {len(matches)} RELEVANT NEWS ITEMS!")
    
    # 4. Send alert
    alert_msg = format_alert_message(matches)
    
    if alert_msg:
        print("\n" + "="*50)
        print(alert_msg)
        print("="*50)
        
        send_telegram_alert(alert_msg)
    
    print("\nDone.")


if __name__ == "__main__":
    main()
