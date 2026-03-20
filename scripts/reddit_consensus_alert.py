#!/usr/bin/env python3
"""
Reddit Consensus Alert

Fetches r/SoccerBetting daily consensus and sends to Telegram.
Runs 1x daily via GitHub Actions.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers.reddit_tipsters import (
    get_daily_picks_thread,
    parse_tipster_comments,
    build_consensus,
    format_reddit_summary
)
import requests


def send_telegram(message: str):
    """Send Telegram alert"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")  # or PUBLIC
    
    if not token or not chat_id:
        print("Telegram credentials not set")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("Telegram alert sent")
        else:
            print(f"Telegram error: {resp.status_code}")
    except Exception as e:
        print(f"Telegram failed: {e}")


def main():
    print("="*60)
    print("REDDIT CONSENSUS ALERT")
    print("="*60)
    
    thread_url = get_daily_picks_thread()
    
    if not thread_url:
        print("No Daily Picks Thread found")
        send_telegram("_Reddit Consensus: No thread found today_")
        return
    
    print(f"Thread: {thread_url}\n")
    
    picks = parse_tipster_comments(thread_url)
    print(f"Found {len(picks)} picks\n")
    
    if not picks:
        send_telegram("_Reddit Consensus: No picks found_")
        return
    
    consensus = build_consensus(picks)
    
    if not consensus:
        msg = f"_Reddit Consensus: {len(picks)} picks found, but no consensus (need 2+ tipsters per match)_"
        send_telegram(msg)
        print(msg)
        return
    
    summary = format_reddit_summary(consensus, top_n=10)
    print(summary)
    print("\nSending to Telegram...")
    
    send_telegram(f"`{summary}`")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
