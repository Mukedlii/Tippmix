#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test if a Telegram channel exists and is accessible
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
API_HASH = "54620b16e0cd77b9180d5d8db79ec6f5"
SESSION_STRING = "1BJWap1wBu7ITLUiFdktD4rIP4GlHznNAxJX81Cx5U5Lds_cA6tYt9M-FWpdKTCemMZthIspKeBTS9pNWBB4xvxZwFNvntF3frrW5MSXI1_QE97DWtVo4JK7-ObyYvdNCmMBXitdxZ-Apbp3IeLX5krOLm3qf6S5PKpmNRXdHu5anbt26pIS6ss3Pxd1ldKjlY4xdVW6wiHywSPUpVjr-YN7jfiI79vDxn7Hykr4JKVEh6T8cBmJjDvh_fZRYpiEi5zgAkcR59d8AHfQ4ETZoaUM_XYKYgce2GL4Qai2N7kAykGoooeUHzT1iz4FumszjiKVZiFbnkL68z5qyYDfpdaF4ww_3k7w="

# Test channels (popular football/betting)
TEST_CHANNELS = [
    "@bettingtipschannel",
    "@footballtips",
    "@soccertips",
    "@bettingtips",
    "@freebets",
    "@footynews",
    "@football",
    "@soccerbetting",
]

async def test_channel(client, channel):
    """Test if channel exists and get info"""
    try:
        entity = await client.get_entity(channel)
        # Get last message to confirm access
        messages = await client.get_messages(entity, limit=1)
        
        print(f"✅ {channel}")
        print(f"   Title: {entity.title if hasattr(entity, 'title') else 'N/A'}")
        print(f"   Subscribers: {entity.participants_count if hasattr(entity, 'participants_count') else 'Unknown'}")
        if messages:
            print(f"   Last message: {messages[0].date}")
        print()
        return True
    except Exception as e:
        print(f"❌ {channel}: {str(e)[:80]}")
        return False

async def main():
    print("🔍 Testing Telegram Channels\n")
    print("=" * 70)
    
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()
    
    working = []
    
    for channel in TEST_CHANNELS:
        if await test_channel(client, channel):
            working.append(channel)
    
    print("=" * 70)
    print(f"\n✅ Working channels ({len(working)}):")
    for ch in working:
        print(f"  {ch}")
    
    await client.disconnect()

asyncio.run(main())
