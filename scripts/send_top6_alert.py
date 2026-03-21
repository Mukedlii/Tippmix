#!/usr/bin/env python3
"""
Phase 5 - TOP 6 Alert System
Format and send daily TOP 6 AI consensus picks to Telegram VIP
"""

import os
import sys
import io
import requests
from datetime import datetime

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.storage.tipster_tracking import get_top6_consensus


def generate_combo_bets(top6_picks):
    """
    Generate combo bets from TOP 6 picks
    
    Returns:
        List of combo bets with odds
    """
    
    combos = []
    
    # Extract odds (use recommended_odds or average)
    picks_with_odds = []
    for pick in top6_picks:
        odds = pick.get('recommended_odds')
        if not odds or odds <= 0:
            odds = 1.75  # Default if missing
        
        picks_with_odds.append({
            'match': f"{pick['home_team']} vs {pick['away_team']}",
            'selection': pick['selection'],
            'odds': odds
        })
    
    if len(picks_with_odds) < 4:
        return combos  # Need at least 4 for combos
    
    # 6-way (all 6)
    if len(picks_with_odds) == 6:
        total_odds = 1.0
        for pick in picks_with_odds:
            total_odds *= pick['odds']
        
        combos.append({
            'size': 6,
            'matches': [p['match'] for p in picks_with_odds],
            'total_odds': total_odds
        })
    
    # 5-way (best 5 by confidence)
    if len(picks_with_odds) >= 5:
        best_5 = sorted(
            zip(top6_picks, picks_with_odds),
            key=lambda x: x[0].get('ai_confidence', 0),
            reverse=True
        )[:5]
        
        total_odds = 1.0
        for _, pick in best_5:
            total_odds *= pick['odds']
        
        combos.append({
            'size': 5,
            'matches': [p['match'] for _, p in best_5],
            'total_odds': total_odds
        })
    
    # 4-way (best 4 by confidence)
    if len(picks_with_odds) >= 4:
        best_4 = sorted(
            zip(top6_picks, picks_with_odds),
            key=lambda x: x[0].get('ai_confidence', 0),
            reverse=True
        )[:4]
        
        total_odds = 1.0
        for _, pick in best_4:
            total_odds *= pick['odds']
        
        combos.append({
            'size': 4,
            'matches': [p['match'] for _, p in best_4],
            'total_odds': total_odds
        })
    
    return combos


def format_telegram_message(top6_picks, combos):
    """
    Format TOP 6 + combos as Telegram message
    """
    
    lines = []
    
    # Header
    today = datetime.now().strftime("%Y-%m-%d")
    lines.append("🤖 **AI TIPSTER CONSENSUS**")
    lines.append(f"📅 {today}")
    lines.append("")
    lines.append("🎯 **TOP 6 BIZTOSNAK TŰNŐ MECCS**")
    lines.append("―――――――――――――――――――――――")
    lines.append("")
    
    # TOP 6 picks
    for i, pick in enumerate(top6_picks, 1):
        match = f"{pick['home_team']} vs {pick['away_team']}"
        selection = pick['selection']
        
        # Confidence
        confidence = pick.get('ai_confidence', pick.get('consensus_strength', 0))
        confidence_pct = int(confidence * 100)
        
        # Tipster stats
        tipster_count = pick.get('tipster_count', 0)
        qualified_count = pick.get('qualified_tipster_count', 0)
        
        # Emoji based on confidence
        if confidence_pct >= 80:
            emoji = "🔥"
        elif confidence_pct >= 70:
            emoji = "⭐"
        else:
            emoji = "📍"
        
        lines.append(f"{emoji} **#{i} - {match}**")
        lines.append(f"   **Tipp:** {selection}")
        lines.append(f"   **Tipsterek:** {tipster_count} total, {qualified_count} qualified")
        lines.append(f"   **AI Konfidencia:** {confidence_pct}%")
        
        # Reasoning (if available)
        if pick.get('ai_reasoning'):
            reasoning = pick['ai_reasoning'][:150]  # Truncate long
            lines.append(f"   💡 _{reasoning}_")
        
        lines.append("")
    
    # Combos
    if combos:
        lines.append("🔢 **KOMBINÁLÓ TIPPEK**")
        lines.append("―――――――――――――――――――――――")
        lines.append("")
        
        for combo in combos:
            size = combo['size']
            odds = combo['total_odds']
            
            lines.append(f"**{size}-es kombo:** @{odds:.2f}")
            for match in combo['matches']:
                lines.append(f"  • {match}")
            lines.append("")
    
    # Footer
    lines.append("―――――――――――――――――――――――")
    lines.append("_🤖 AI elemzés OpenAI GPT-4o-mini alapján_")
    lines.append("_📊 Qualified tipsters: win rate >= 55%, ROI >= 5%, min 20 tip_")
    lines.append("")
    lines.append("🍀 **SOK SIKERT!** 🍀")
    
    return "\n".join(lines)


def send_telegram_message(message):
    """
    Send message to Telegram VIP channel
    """
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '8238287955:AAEo87ADOjZx6qcCW1eEYN6YV1klAzZ_8bs')
    chat_id = os.getenv('TELEGRAM_VIP_CHAT_ID', '-1003341312269')
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print("✅ Alert sent to Telegram VIP!")
            return True
        else:
            print(f"❌ Telegram API error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")
        return False


def main():
    print("\n" + "="*60)
    print(f"📲 TOP 6 ALERT SENDER - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60 + "\n")
    
    # Get today's TOP 6
    print("📊 Loading TOP 6 consensus picks...\n")
    
    today = datetime.now().strftime("%Y-%m-%d")
    top6_picks = get_top6_consensus(today)
    
    if not top6_picks:
        print("⚠️  No TOP 6 picks found for today")
        print("   Run ai_consensus.py first!\n")
        return
    
    print(f"✅ Found {len(top6_picks)} TOP 6 picks\n")
    
    # Generate combos
    print("🔢 Generating combo bets...\n")
    combos = generate_combo_bets(top6_picks)
    
    if combos:
        for combo in combos:
            print(f"  {combo['size']}-way: @{combo['total_odds']:.2f}")
    else:
        print("  ⚠️  Not enough picks for combos (need 4+)")
    
    print()
    
    # Format message
    print("📝 Formatting Telegram message...\n")
    message = format_telegram_message(top6_picks, combos)
    
    # Preview
    print("―" * 60)
    print("MESSAGE PREVIEW:")
    print("―" * 60)
    print(message)
    print("―" * 60)
    print()
    
    # Send
    print("📲 Sending to Telegram VIP channel...\n")
    success = send_telegram_message(message)
    
    if success:
        print("\n" + "="*60)
        print("✅ ALERT SENT SUCCESSFULLY!")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print("❌ FAILED TO SEND ALERT")
        print("="*60 + "\n")


if __name__ == '__main__':
    main()
