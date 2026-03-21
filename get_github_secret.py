#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Get GitHub Secret values (they can't be read, but we can check if they exist)
For Telegram credentials, you need the actual values.

If you don't have them:
1. Bot Token: Talk to @BotFather on Telegram
2. VIP Chat ID: Forward a message from the channel to @userinfobot
"""
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("❌ GitHub Secrets cannot be READ (write-only)")
print("")
print("📋 You need these values:")
print("")
print("1. TELEGRAM_BOT_TOKEN")
print("   - Talk to @BotFather on Telegram")
print("   - Send: /newbot")
print("   - Follow instructions")
print("   - Copy the token")
print("")
print("2. TELEGRAM_VIP_CHAT_ID")
print("   - Go to your VIP channel")
print("   - Forward any message to @userinfobot")
print("   - Copy the 'Forwarded from chat' ID (negative number)")
print("")
print("Then run:")
print('  $env:TELEGRAM_BOT_TOKEN="<token>"')
print('  $env:TELEGRAM_VIP_CHAT_ID="<chat_id>"')
print("  python send_reddit_tips_now.py")
