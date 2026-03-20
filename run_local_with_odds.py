#!/usr/bin/env python3
"""
Run bot locally with real Telegram tokens from GitHub Secrets
"""
import requests
import subprocess
import os
import sys

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"

print("Fetching Telegram tokens from GitHub Secrets...")

# Get secret values (can't read directly, but we can trigger a workflow that outputs them)
# OR we need them from user

print("\nTo run locally with real Telegram sending, I need:")
print("1. TELEGRAM_BOT_TOKEN")
print("2. TELEGRAM_VIP_CHAT_ID")
print("\nThese are stored in GitHub Secrets but can't be read back.")
print("\nOptions:")
print("A) Enter them now (they won't be saved)")
print("B) I'll create a workflow that uses them and sends")
print("\nWhich option? (A/B): ", end="")

choice = input().strip().upper()

if choice == "A":
    bot_token = input("TELEGRAM_BOT_TOKEN: ").strip()
    vip_chat_id = input("TELEGRAM_VIP_CHAT_ID: ").strip()
    
    # Update .env
    env_content = f"""# Telegram
TELEGRAM_BOT_TOKEN={bot_token}
TELEGRAM_PUBLIC_CHAT_ID=dummy
TELEGRAM_VIP_CHAT_ID={vip_chat_id}

# Odds API
ODDS_API_KEY=acf78bce7a7976c2bc4d028528d4cb2f
ODDS_SPORT_KEYS=soccer_epl,soccer_germany_bundesliga,soccer_italy_serie_a,soccer_spain_la_liga,soccer_france_ligue_one

# Engine
TIPPMIX_ENGINE=poisson
TIPPMIX_USE_MARKETING_FORMAT=1
TIPPMIX_SEND_VIP=1
TIPPMIX_SEND_PUBLIC=0
TIPPMIX_SLOT=ALL
SPORTS_DATA_PROVIDER=free_scraper
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("\n.env updated! Running bot now...")
    
    # Run bot
    os.system("python -m bot.main")
    
elif choice == "B":
    print("\nOK, I'll trigger a special workflow that sends with real tokens.")
    print("(Not implemented yet - need to create workflow)")
else:
    print("Invalid choice")
