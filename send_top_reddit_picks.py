#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Send TOP Reddit picks to Telegram VIP (no consensus needed)
"""
import sys
import io
import os
import requests
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers.reddit_tipsters import (
    get_all_picks_threads,
    parse_tipster_comments
)

# Get Reddit tips
print("📥 Fetching Reddit tips...")
threads = get_all_picks_threads()

if not threads:
    print("❌ No threads found")
    sys.exit(1)

all_picks = []
for sub, url in threads.items():
    if url:
        picks = parse_tipster_comments(url)
        print(f"  r/{sub}: {len(picks)} picks")
        all_picks.extend(picks)

if not all_picks:
    print("❌ No picks found")
    sys.exit(1)

# Group by tipster
by_tipster = defaultdict(list)
for pick in all_picks:
    tipster = pick.get('tipster', 'Unknown')
    by_tipster[tipster].append(pick)

# Find tipsters with multiple picks (portfolios)
portfolios = {t: picks for t, picks in by_tipster.items() if len(picks) >= 3}

print(f"\n📊 {len(all_picks)} picks from {len(by_tipster)} tipsters")
print(f"   {len(portfolios)} portfolios (3+ picks)")

# Build message
message = "🎯 **REDDIT DAILY PICKS**\n"
message += f"_r/SoccerBetting - {len(all_picks)} tips_\n\n"

if portfolios:
    message += "**📦 PORTFOLIOS (3+ picks)**\n\n"
    for tipster, picks in list(portfolios.items())[:2]:  # Top 2
        message += f"**{tipster}** ({len(picks)} picks)\n"
        for pick in picks[:5]:  # Max 5 per portfolio
            match = pick.get('match', 'Unknown')[:40]
            pick_type = pick.get('pick', '?')
            odds = pick.get('odds', 0)
            message += f"├ {match}\n"
            message += f"│ └ {pick_type}"
            if odds:
                message += f" @ {odds:.2f}"
            message += "\n"
        message += "\n"

# Top individual picks
message += "**⭐ TOP INDIVIDUAL PICKS**\n\n"
top_picks = sorted([p for p in all_picks if p.get('confidence', 0) >= 4], 
                   key=lambda x: x.get('confidence', 0), reverse=True)[:5]

for pick in top_picks:
    match = pick.get('match', 'Unknown')[:40]
    pick_type = pick.get('pick', '?')
    odds = pick.get('odds', 0)
    tipster = pick.get('tipster', '?')
    conf = pick.get('confidence', 0)
    
    message += f"**{match}**\n"
    message += f"└ {pick_type}"
    if odds:
        message += f" @ {odds:.2f}"
    message += f" (★{conf}/5 by {tipster})\n\n"

message += f"_Source: r/SoccerBetting Daily Picks Thread_"

print("\n" + "="*70)
print(message)
print("="*70)

# Send to Telegram
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VIP_CHAT_ID = os.getenv("TELEGRAM_VIP_CHAT_ID")

if not BOT_TOKEN or not VIP_CHAT_ID:
    print("\n⚠️ Set TELEGRAM_BOT_TOKEN and TELEGRAM_VIP_CHAT_ID env vars!")
    print("\nTo get them:")
    print("  TELEGRAM_BOT_TOKEN: @BotFather on Telegram")
    print("  TELEGRAM_VIP_CHAT_ID: Forward channel message to @userinfobot")
    sys.exit(0)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": VIP_CHAT_ID,
    "text": message,
    "parse_mode": "Markdown"
}

try:
    resp = requests.post(url, json=payload, timeout=15)
    if resp.status_code == 200:
        print("\n✅ Sent to Telegram VIP!")
    else:
        print(f"\n❌ Telegram error: {resp.status_code}")
        print(resp.text)
except Exception as e:
    print(f"\n❌ Failed: {e}")
