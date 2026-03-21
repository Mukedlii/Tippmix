#!/usr/bin/env python3
"""
Combined Tipster Alert

Combines tips from multiple sources:
- Reddit (r/SoccerBetting, r/SoccerPredictions, r/sportsbetting)
- Telegram channels (free tipsters)
- BettingExpert.com (fallback, if Selenium available)

Sends combined consensus to Telegram.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers.reddit_tipsters import (
    get_all_picks_threads,
    parse_tipster_comments,
    build_consensus as build_reddit_consensus,
)

# Telegram tipsters (optional)
TELEGRAM_ENABLED = False
try:
    from bot.providers.telegram_tipsters import scrape_telegram_tips_sync, build_telegram_consensus
    if os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH"):
        TELEGRAM_ENABLED = True
except:
    pass

import requests


def send_telegram(message: str):
    """Send Telegram alert"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")
    
    if not token or not chat_id:
        print("Telegram bot credentials not set")
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
            print("✅ Telegram alert sent")
        else:
            print(f"❌ Telegram error: {resp.status_code}")
    except Exception as e:
        print(f"❌ Telegram failed: {e}")


def main():
    print("="*70)
    print("COMBINED TIPSTER CONSENSUS ALERT")
    print("="*70)
    
    all_sources = []
    
    # ===== REDDIT =====
    print("\n📱 REDDIT")
    print("-" * 70)
    
    reddit_threads = get_all_picks_threads()
    
    if reddit_threads:
        print(f"Found {len(reddit_threads)} threads:")
        for sub, url in reddit_threads.items():
            print(f"  ✅ r/{sub}")
        
        reddit_picks = []
        for sub, thread_url in reddit_threads.items():
            if thread_url:
                picks = parse_tipster_comments(thread_url)
                print(f"  r/{sub}: {len(picks)} picks")
                reddit_picks.extend(picks)
        
        if reddit_picks:
            reddit_consensus = build_reddit_consensus(reddit_picks, min_tipsters=2)
            print(f"  📊 {len(reddit_consensus)} Reddit consensus picks")
            all_sources.append(("Reddit", reddit_consensus))
        else:
            print("  ⚠️ No picks found")
    else:
        print("  ⚠️ No threads found")
    
    # ===== TELEGRAM =====
    if TELEGRAM_ENABLED:
        print("\n📱 TELEGRAM CHANNELS")
        print("-" * 70)
        
        try:
            telegram_tips = scrape_telegram_tips_sync(hours_back=24, max_messages=30)
            
            if telegram_tips:
                print(f"  ✅ {len(telegram_tips)} tips from Telegram")
                telegram_consensus = build_telegram_consensus(telegram_tips, min_tips=2)
                print(f"  📊 {len(telegram_consensus)} Telegram consensus picks")
                all_sources.append(("Telegram", telegram_consensus))
            else:
                print("  ⚠️ No Telegram tips")
        except Exception as e:
            print(f"  ❌ Telegram error: {e}")
    else:
        print("\n⏭️  TELEGRAM: Disabled (no API credentials)")
    
    # ===== COMBINED CONSENSUS =====
    print("\n" + "="*70)
    print("COMBINED CONSENSUS")
    print("="*70)
    
    if not all_sources:
        msg = "_No tipster consensus found from any source_"
        print(msg)
        send_telegram(msg)
        return
    
    # Build combined message
    lines = [
        "🔥 *TIPSTER CONSENSUS - COMBINED*",
        f"📅 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    
    total_picks = 0
    
    for source_name, consensus in all_sources:
        if not consensus:
            continue
        
        total_picks += len(consensus)
        
        lines.append(f"📊 *{source_name.upper()}* ({len(consensus)} picks)")
        lines.append("")
        
        for i, pick in enumerate(consensus[:5], 1):  # Top 5 per source
            match = pick.get('match', 'Unknown')
            pick_type = pick.get('pick', 'Unknown')
            
            # Handle different consensus formats
            if 'avg_odds' in pick:
                odds = pick['avg_odds']
            elif 'odds' in pick:
                odds = pick['odds']
            else:
                odds = 0
            
            if 'tipster_count' in pick:
                count = pick['tipster_count']
                count_label = "tipsters"
            elif 'channel_count' in pick:
                count = pick['channel_count']
                count_label = "channels"
            else:
                count = 0
                count_label = "sources"
            
            lines.append(f"{i}. *{match}*")
            lines.append(f"   🎯 {pick_type} @ {odds}")
            lines.append(f"   👥 {count} {count_label}")
            lines.append("")
    
    if total_picks == 0:
        msg = "_Tips found but no consensus (need 2+ sources per match)_"
        print(msg)
        send_telegram(msg)
        return
    
    lines.append("---")
    sources_list = ", ".join(s[0] for s in all_sources)
    lines.append(f"_Források: {sources_list}_")
    
    message = "\n".join(lines)
    
    print("\n" + message)
    print("\n" + "="*70)
    print("Sending to Telegram...")
    send_telegram(message)


if __name__ == "__main__":
    main()
