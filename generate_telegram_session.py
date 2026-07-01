#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Telegram session file for headless use
Run this ONCE locally, then upload the session string to GitHub Secrets
"""
import sys
import io
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

API_ID = 37692359
API_HASH = "<your_telegram_api_hash>"

print("🔐 Generating Telegram Session")
print("=" * 70)
print("\nThis will ask for your phone number and Telegram code.")
print("Complete the auth, then copy the SESSION STRING to GitHub Secrets.\n")

async def main():
    # Use StringSession (returns a string you can save)
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    await client.start()
    
    session_string = client.session.save()
    
    print("\n" + "=" * 70)
    print("✅ AUTH SUCCESSFUL!")
    print("=" * 70)
    print("\n📋 SESSION STRING (copy this to GitHub Secrets):\n")
    print(session_string)
    print("\n" + "=" * 70)
    print("\nGitHub Secret setup:")
    print("  Name: TELEGRAM_SESSION_STRING")
    print(f"  Value: {session_string}")
    print("\nAfter adding the secret, the workflow will work headlessly!")
    print("=" * 70)
    
    await client.disconnect()

# Run async main
asyncio.run(main())
