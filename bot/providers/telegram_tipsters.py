#!/usr/bin/env python3
"""
Telegram Tipster Channels Scraper

Reads public football tips from Telegram channels.
Requires Telethon library and Telegram API credentials.

Setup:
1. Get API credentials: https://my.telegram.org/apps
2. Set environment variables:
   - TELEGRAM_API_ID
   - TELEGRAM_API_HASH
   - TELEGRAM_SESSION_NAME (optional, default: "tippmix_scraper")
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

try:
    from telethon import TelegramClient
    from telethon.tl.types import Channel
    from telethon.sessions import StringSession
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    print("[TelegramTips] Telethon not installed. Run: pip install telethon")


# Popular free football tipster channels
# Note: These are EXAMPLE channel names - replace with actual working channels
DEFAULT_CHANNELS = [
    "@football",                # Telegram official football channel (test)
    "@FootballPredictions24",   # Daily predictions (if exists)
    # Add more VERIFIED channels after testing
    # Check: https://t.me/<channel_name> before adding
]


async def get_telegram_api_credentials() -> tuple:
    """
    Get Telegram API credentials from environment
    
    Returns:
        (api_id, api_hash, session_string)
    
    Raises:
        ValueError if credentials not set
    """
    # Try session string first (for headless/GitHub Actions)
    session_string = os.getenv("TELEGRAM_SESSION_STRING")
    
    if session_string:
        # Session string includes auth - just need API ID/Hash for client init
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        
        if not api_id or not api_hash:
            raise ValueError("TELEGRAM_SESSION_STRING set but missing TELEGRAM_API_ID/HASH")
        
        return int(api_id), api_hash, session_string
    
    # Fallback to interactive login (local development)
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    
    if not api_id or not api_hash:
        raise ValueError(
            "Telegram API credentials not set!\n"
            "Get them from: https://my.telegram.org/apps\n"
            "Then set:\n"
            "  TELEGRAM_API_ID=your_api_id\n"
            "  TELEGRAM_API_HASH=your_api_hash\n"
            "  TELEGRAM_SESSION_STRING=... (optional, for headless)"
        )
    
    return int(api_id), api_hash, None


async def scrape_telegram_channel(
    client: TelegramClient,
    channel_username: str,
    hours_back: int = 24,
    max_messages: int = 50
) -> List[Dict]:
    """
    Scrape recent messages from a Telegram channel
    
    Args:
        client: Telethon client
        channel_username: Channel username (e.g., "@FreeSuperTips")
        hours_back: How many hours back to scrape
        max_messages: Maximum number of messages to fetch
    
    Returns:
        List of parsed tips
    """
    
    tips = []
    
    try:
        # Get channel entity
        channel = await client.get_entity(channel_username)
        
        # Calculate time threshold (use UTC with timezone)
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        print(f"[Telegram] Scraping {channel_username} (last {hours_back}h)...")
        
        # Fetch recent messages
        async for message in client.iter_messages(channel, limit=max_messages):
            # Skip if too old
            if message.date < time_threshold:
                break
            
            # Skip if no text
            if not message.text:
                continue
            
            text = message.text
            
            # Parse tip from text
            tip = parse_telegram_tip(text, channel_username)
            
            if tip:
                tip['message_id'] = message.id
                tip['date'] = message.date
                tips.append(tip)
        
        print(f"[Telegram] {channel_username}: {len(tips)} tips found")
        
    except Exception as e:
        print(f"[Telegram] Error scraping {channel_username}: {e}")
    
    return tips


def parse_telegram_tip(text: str, channel: str) -> Optional[Dict]:
    """
    Parse a betting tip from Telegram message text
    
    Common formats:
    - "Arsenal vs Chelsea - Home Win @ 2.50"
    - "Man United to win @ 1.80 ⚽"
    - "BTTS: Liverpool vs Arsenal @ 1.90"
    - "Over 2.5 goals: Real Madrid vs Barcelona @ 2.10"
    
    Returns:
        Dict with tip info or None
    """
    
    # Look for odds pattern first (@ X.XX)
    odds_match = re.search(r'[@:]?\s*(\d+\.\d{1,2})', text)
    if not odds_match:
        return None  # No odds = not a tip
    
    odds = float(odds_match.group(1))
    
    # Look for match pattern: "Team A vs Team B"
    match_pattern = re.search(
        r'([A-Za-z\s\.\-]+?)\s+vs\.?\s+([A-Za-z\s\.\-]+?)(?:\s|$|@|-)',
        text,
        re.IGNORECASE
    )
    
    match = None
    if match_pattern:
        match = f"{match_pattern.group(1).strip()} vs {match_pattern.group(2).strip()}"
    
    # Determine pick type
    pick = None
    text_lower = text.lower()
    
    if 'btts' in text_lower or 'both teams' in text_lower or 'both to score' in text_lower:
        pick = "BTTS Yes"
    elif 'over' in text_lower:
        over_match = re.search(r'over\s+(\d+\.?\d*)', text_lower)
        pick = f"Over {over_match.group(1)}" if over_match else "Over 2.5"
    elif 'under' in text_lower:
        under_match = re.search(r'under\s+(\d+\.?\d*)', text_lower)
        pick = f"Under {under_match.group(1)}" if under_match else "Under 2.5"
    elif any(w in text_lower for w in ['home win', 'home to win', 'win home', 'victory home']):
        pick = "Home Win"
    elif any(w in text_lower for w in ['away win', 'away to win', 'win away', 'victory away']):
        pick = "Away Win"
    elif 'draw' in text_lower or 'x' == text_lower.strip():
        pick = "Draw"
    elif ' to win' in text_lower or ' win @' in text_lower:
        # Generic "Team to win @ odds"
        team_match = re.search(r'([A-Za-z\s]+?)\s+(?:to\s+)?win', text, re.IGNORECASE)
        if team_match:
            pick = f"{team_match.group(1).strip()} Win"
    
    # Only return if we have a pick or match
    if not pick and not match:
        return None
    
    return {
        "match": match or "Unknown match",
        "pick": pick or "Unknown pick",
        "odds": odds,
        "source": f"Telegram:{channel}",
        "raw_text": text[:200]  # for debugging
    }


async def scrape_all_telegram_channels(
    channels: List[str] = None,
    hours_back: int = 24,
    max_messages: int = 50
) -> List[Dict]:
    """
    Scrape multiple Telegram channels
    
    Args:
        channels: List of channel usernames (default: DEFAULT_CHANNELS)
        hours_back: How many hours back to scrape
        max_messages: Max messages per channel
    
    Returns:
        Combined list of all tips
    """
    
    if not TELETHON_AVAILABLE:
        print("[TelegramTips] Telethon not installed!")
        return []
    
    if channels is None:
        channels = DEFAULT_CHANNELS
    
    try:
        api_id, api_hash, session_data = await get_telegram_api_credentials()
    except ValueError as e:
        print(f"[TelegramTips] {e}")
        return []
    
    all_tips = []
    
    # Create Telegram client with StringSession if available
    if session_data and isinstance(session_data, str) and session_data.startswith("1"):
        # Use StringSession (headless mode)
        session = StringSession(session_data)
        print("[Telegram] Using session string (headless mode)")
    else:
        # Use file-based session (interactive mode)
        session = session_data or "tippmix_scraper"
        print("[Telegram] Using file-based session (interactive mode)")
    
    async with TelegramClient(session, api_id, api_hash) as client:
        print(f"[Telegram] Connected to Telegram")
        
        for channel in channels:
            tips = await scrape_telegram_channel(
                client,
                channel,
                hours_back=hours_back,
                max_messages=max_messages
            )
            all_tips.extend(tips)
    
    print(f"\n[Telegram] Total: {len(all_tips)} tips from {len(channels)} channels")
    
    return all_tips


def build_telegram_consensus(tips: List[Dict], min_tips: int = 2) -> List[Dict]:
    """
    Build consensus from Telegram tips
    """
    
    # Group by match
    by_match = {}
    
    for tip in tips:
        match = tip.get('match', '').lower().strip()
        if not match or match == 'unknown match':
            continue
        
        if match not in by_match:
            by_match[match] = []
        
        by_match[match].append(tip)
    
    consensus = []
    
    for match, match_tips in by_match.items():
        # Group by pick
        by_pick = {}
        
        for tip in match_tips:
            pick = tip.get('pick', 'Unknown')
            if pick not in by_pick:
                by_pick[pick] = []
            by_pick[pick].append(tip)
        
        # Find picks with min_tips
        for pick, pick_tips in by_pick.items():
            if len(pick_tips) >= min_tips:
                avg_odds = sum(t.get('odds', 0) for t in pick_tips) / len(pick_tips)
                channels = list(set(t.get('source') for t in pick_tips))
                
                consensus.append({
                    "match": match_tips[0].get('match'),  # original case
                    "pick": pick,
                    "channel_count": len(pick_tips),
                    "avg_odds": round(avg_odds, 2),
                    "channels": channels,
                })
    
    # Sort by channel count
    consensus.sort(key=lambda x: x['channel_count'], reverse=True)
    
    return consensus


def format_telegram_summary(consensus: List[Dict], top_n: int = 10) -> str:
    """
    Format Telegram consensus for output
    """
    if not consensus:
        return "_No Telegram consensus found_"
    
    lines = [
        "📱 *TELEGRAM CONSENSUS*",
        f"📊 {len(consensus)} matches with 2+ channels",
        "",
    ]
    
    for i, pick in enumerate(consensus[:top_n], 1):
        match = pick['match']
        pick_type = pick['pick']
        count = pick['channel_count']
        odds = pick['avg_odds']
        
        lines.append(f"*{i}. {match}*")
        lines.append(f"   🎯 {pick_type} @ {odds}")
        lines.append(f"   📱 {count} channels")
        lines.append("")
    
    lines.append("---")
    lines.append("_Forrás: Free Telegram tipster channels_")
    
    return "\n".join(lines)


# Sync wrapper for easier usage
def scrape_telegram_tipsters(
    channels: List[str] = None,
    hours_back: int = 24,
    max_messages: int = 50
) -> List[Dict]:
    """
    Synchronous wrapper for scraping Telegram channels
    """
    import asyncio
    
    try:
        return asyncio.run(scrape_all_telegram_channels(channels, hours_back, max_messages))
    except Exception as e:
        print(f"[TelegramTips] Error: {e}")
        return []


if __name__ == "__main__":
    import asyncio
    
    print("="*60)
    print("TELEGRAM TIPSTER SCRAPER TEST")
    print("="*60)
    
    if not TELETHON_AVAILABLE:
        print("\n❌ Telethon not installed!")
        print("\nInstall: pip install telethon")
        print("\nThen get API credentials from: https://my.telegram.org/apps")
        exit(1)
    
    # Check credentials
    try:
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        
        if not api_id or not api_hash:
            print("\n⚠️ Telegram API credentials not set!")
            print("\nGet them from: https://my.telegram.org/apps")
            print("\nThen set:")
            print("  TELEGRAM_API_ID=your_api_id")
            print("  TELEGRAM_API_HASH=your_api_hash")
            exit(1)
        
        print(f"\n✅ API credentials found")
        print(f"   API ID: {api_id}")
        print(f"   Session: {os.getenv('TELEGRAM_SESSION_NAME', 'tippmix_scraper')}")
        
        # Test with a small subset
        test_channels = DEFAULT_CHANNELS[:2]  # First 2 channels only
        
        print(f"\nTesting with {len(test_channels)} channels:")
        for ch in test_channels:
            print(f"  - {ch}")
        
        print("\nScraping (last 24h)...\n")
        
        tips = asyncio.run(scrape_all_telegram_channels(
            channels=test_channels,
            hours_back=24,
            max_messages=30
        ))
        
        if tips:
            print(f"\n✅ {len(tips)} tips found\n")
            
            # Show first 3
            for i, tip in enumerate(tips[:3], 1):
                print(f"{i}. {tip['match']}")
                print(f"   Pick: {tip['pick']} @ {tip['odds']}")
                print(f"   Source: {tip['source']}")
                print()
            
            # Build consensus
            consensus = build_telegram_consensus(tips, min_tips=2)
            
            if consensus:
                print(f"\n{len(consensus)} consensus picks\n")
                summary = format_telegram_summary(consensus)
                print(summary)
            else:
                print("\nNo consensus (need 2+ channels per match)")
        else:
            print("\n⚠️ No tips found")
            print("   - Channels might be private/restricted")
            print("   - Or no recent tips posted")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
