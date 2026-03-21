#!/usr/bin/env python3
"""
Daily Recap - Evening Summary
Check today's TOP 6 results and send recap to Telegram
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

from bot.storage.tipster_tracking import get_db


def get_todays_consensus():
    """Get today's TOP 6 AI consensus picks with results"""
    
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    c.execute("""
        SELECT 
            ac.id, ac.home_team, ac.away_team, ac.selection,
            ac.recommended_odds, ac.ai_confidence, ac.rank_position,
            ac.is_settled, ac.won, ac.actual_score, ac.roi
        FROM ai_consensus ac
        WHERE ac.analysis_date = ?
        AND ac.is_top6 = 1
        ORDER BY ac.rank_position ASC
    """, (today,))
    
    picks = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return picks


def calculate_combo_results(picks):
    """Calculate combo bet results"""
    
    combos = []
    
    # Filter settled picks
    settled = [p for p in picks if p['is_settled']]
    
    if len(settled) < 4:
        return combos  # Need at least 4 for combos
    
    # 6-way
    if len(settled) == 6:
        all_won = all(p['won'] for p in settled)
        total_odds = 1.0
        for p in settled:
            total_odds *= (p['recommended_odds'] or 1.75)
        
        combos.append({
            'size': 6,
            'won': all_won,
            'odds': total_odds,
            'roi': (total_odds - 1.0) if all_won else -1.0
        })
    
    # 5-way (best 5 by confidence)
    if len(settled) >= 5:
        best_5 = sorted(settled, key=lambda x: x['ai_confidence'] or 0, reverse=True)[:5]
        all_won = all(p['won'] for p in best_5)
        total_odds = 1.0
        for p in best_5:
            total_odds *= (p['recommended_odds'] or 1.75)
        
        combos.append({
            'size': 5,
            'won': all_won,
            'odds': total_odds,
            'roi': (total_odds - 1.0) if all_won else -1.0
        })
    
    # 4-way (best 4 by confidence)
    if len(settled) >= 4:
        best_4 = sorted(settled, key=lambda x: x['ai_confidence'] or 0, reverse=True)[:4]
        all_won = all(p['won'] for p in best_4)
        total_odds = 1.0
        for p in best_4:
            total_odds *= (p['recommended_odds'] or 1.75)
        
        combos.append({
            'size': 4,
            'won': all_won,
            'odds': total_odds,
            'roi': (total_odds - 1.0) if all_won else -1.0
        })
    
    return combos


def format_recap_message(picks, combos):
    """Format daily recap message"""
    
    lines = []
    
    # Header
    today = datetime.now().strftime("%Y-%m-%d")
    lines.append("📊 **NAPI ÖSSZEFOGLALÓ**")
    lines.append(f"📅 {today}")
    lines.append("")
    
    # Check if picks settled
    settled_count = sum(1 for p in picks if p['is_settled'])
    won_count = sum(1 for p in picks if p['is_settled'] and p['won'])
    
    if settled_count == 0:
        lines.append("⏳ **Még nincs eredmény**")
        lines.append("A meccsek még nem értek véget.")
        lines.append("")
        return "\n".join(lines)
    
    # Summary
    win_rate = (won_count / settled_count * 100) if settled_count > 0 else 0
    lines.append(f"🎯 **TOP 6 EREDMÉNYEK:** {won_count}/{settled_count} ({win_rate:.0f}%)")
    lines.append("―――――――――――――――――――――――")
    lines.append("")
    
    # Individual picks
    for pick in picks:
        if not pick['is_settled']:
            continue
        
        match = f"{pick['home_team']} vs {pick['away_team']}"
        selection = pick['selection']
        score = pick['actual_score'] or "N/A"
        
        if pick['won']:
            emoji = "✅"
            result = "NYERT"
        else:
            emoji = "❌"
            result = "VESZTETT"
        
        lines.append(f"{emoji} **#{pick['rank_position']} - {match}**")
        lines.append(f"   Tipp: {selection} | Eredmény: {score} | **{result}**")
        lines.append("")
    
    # Combos
    if combos:
        lines.append("🔢 **KOMBINÁLÓ EREDMÉNYEK**")
        lines.append("―――――――――――――――――――――――")
        lines.append("")
        
        for combo in combos:
            size = combo['size']
            odds = combo['odds']
            
            if combo['won']:
                emoji = "✅"
                profit = f"+{(odds - 1.0) * 100:.0f}%"
                lines.append(f"{emoji} **{size}-es kombo:** NYERT! @{odds:.2f} ({profit})")
            else:
                emoji = "❌"
                lines.append(f"{emoji} **{size}-es kombo:** Vesztett @{odds:.2f} (-100%)")
            
            lines.append("")
    
    # Overall stats
    avg_roi = sum(p['roi'] or 0 for p in picks if p['is_settled']) / max(settled_count, 1)
    lines.append("―――――――――――――――――――――――")
    lines.append(f"📈 **Átlag ROI (egyedi):** {avg_roi*100:+.1f}%")
    
    if combos:
        best_combo_roi = max(c['roi'] for c in combos)
        lines.append(f"🚀 **Legjobb kombo ROI:** {best_combo_roi*100:+.1f}%")
    
    lines.append("")
    lines.append("―――――――――――――――――――――――")
    lines.append("_🤖 AI Tipster Aggregator System_")
    lines.append("")
    lines.append("🌙 **Jó éjszakát! Holnap újabb tippek!**")
    
    return "\n".join(lines)


def send_telegram_message(message):
    """Send recap to Telegram VIP channel"""
    
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
            print("✅ Recap sent to Telegram VIP!")
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
    print(f"📊 DAILY RECAP - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60 + "\n")
    
    # Get today's picks
    print("📊 Loading today's TOP 6 picks...\n")
    picks = get_todays_consensus()
    
    if not picks:
        print("⚠️  No TOP 6 picks found for today")
        print("   No recap to send.\n")
        return
    
    print(f"✅ Found {len(picks)} TOP 6 picks\n")
    
    # Calculate combos
    print("🔢 Calculating combo results...\n")
    combos = calculate_combo_results(picks)
    
    # Format message
    print("📝 Formatting recap message...\n")
    message = format_recap_message(picks, combos)
    
    # Preview
    print("―" * 60)
    print("RECAP PREVIEW:")
    print("―" * 60)
    print(message)
    print("―" * 60)
    print()
    
    # Send
    print("📲 Sending to Telegram VIP channel...\n")
    success = send_telegram_message(message)
    
    if success:
        print("\n" + "="*60)
        print("✅ RECAP SENT SUCCESSFULLY!")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print("❌ FAILED TO SEND RECAP")
        print("="*60 + "\n")


if __name__ == '__main__':
    main()
