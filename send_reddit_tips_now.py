#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Send Reddit tips to Telegram VIP NOW (bypassing GitHub Actions)
"""
import sys
import io
import os
import requests

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers.reddit_tipsters import (
    get_all_picks_threads,
    parse_tipster_comments,
    build_consensus as build_reddit_consensus
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

# Build consensus
consensus = build_reddit_consensus(all_picks, min_tipsters=2)
print(f"\n📊 {len(consensus)} consensus picks")

if not consensus:
    print("No consensus (need 2+ tipsters)")
    sys.exit(0)

# Format message
message = "🎯 **REDDIT TIPSTER CONSENSUS**\n\n"
for tip in consensus:
    match = tip.get('match', 'Unknown')
    pick = tip.get('pick', 'Unknown')
    tipsters = tip.get('count', 0)
    avg_odds = tip.get('avg_odds', 0)
    
    message += f"**{match}**\n"
    message += f"└ {pick}\n"
    message += f"└ {tipsters} tipsters"
    if avg_odds:
        message += f" @ {avg_odds:.2f}"
    message += f"\n\n"

message += f"_Source: r/SoccerBetting + others_"

print("\n" + "="*70)
print(message)
print("="*70)

# Send to Telegram
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VIP_CHAT_ID = os.getenv("TELEGRAM_VIP_CHAT_ID")

if not BOT_TOKEN or not VIP_CHAT_ID:
    print("\n⚠️ Set TELEGRAM_BOT_TOKEN and TELEGRAM_VIP_CHAT_ID to send!")
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
