"""
bot/telegram_marketing.py

Marketing-optimalizált Telegram üzenetek + inline gombok.
Hasonló formátum mint a profi tippmix botoknál.
"""

from typing import List, Dict, Any, Optional
import os


def create_inline_buttons(
    dashboard_url: str = "https://tippmix.vercel.app",
    betting_site: str = "tippmix",  # tippmix, bet365, unibet
) -> List[List[Dict[str, str]]]:
    """
    Inline gombok a Telegram üzenethez.
    
    Returns:
        List of button rows (each row is a list of buttons)
    """
    buttons = []
    
    # First row: Dashboard + Betting site
    row1 = [
        {"text": "📊 Statisztikák", "url": dashboard_url},
    ]
    
    if betting_site == "tippmix":
        row1.append({"text": "⚽ Tippmix PRO", "url": "https://www.tippmixpro.hu"})
    elif betting_site == "bet365":
        row1.append({"text": "🎰 Bet365", "url": "https://www.bet365.com"})
    elif betting_site == "unibet":
        row1.append({"text": "🎲 Unibet", "url": "https://www.unibet.hu"})
    
    buttons.append(row1)
    
    # Second row: VIP upgrade (optional)
    show_vip_button = os.getenv("TIPPMIX_SHOW_VIP_BUTTON", "1").strip() == "1"
    vip_url = os.getenv("TIPPMIX_VIP_URL", "https://tippmix.vercel.app/vip")
    
    if show_vip_button:
        buttons.append([
            {"text": "💎 VIP Előfizetés", "url": vip_url}
        ])
    
    return buttons


def format_marketing_vip(
    tips: List[Dict[str, Any]],
    combos: List[Dict[str, Any]],
    date_str: str,
    stats: Optional[Dict[str, Any]] = None,
) -> tuple[str, List[List[Dict[str, str]]]]:
    """
    Marketing-optimalizált VIP üzenet.
    
    Args:
        tips: Tippek lista
        combos: Kombók lista
        date_str: Dátum (YYYY.MM.DD.)
        stats: Opcionális stats (win rate, ROI)
    
    Returns:
        (message_text, inline_buttons)
    """
    
    # Header
    lines = [
        "👑⚽️ *SZELVÉNYKIRÁLY VIP*",
        f"📅 {date_str}",
        "",
    ]
    
    # Stats (if available)
    if stats:
        win_rate = stats.get("win_rate", 0)
        roi = stats.get("roi", 0)
        lines.append(f"📊 *Teljesítmény:* {win_rate:.0f}% találat | ROI: {roi:+.1f}%")
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("🏆 *MAI KIEMELT TIPPEK*")
    lines.append("")
    
    # Tips
    for i, tip in enumerate(tips[:6], 1):  # Max 6 kiemelt
        home = tip.get("home_team", "")
        away = tip.get("away_team", "")
        selection = tip.get("selection", "")
        odds = tip.get("odds_estimate")
        odds_txt = f"{odds:.2f}" if odds else "TBA"
        confidence = tip.get("confidence", 3.0)
        
        # Confidence stars
        stars = "⭐" * min(5, max(1, int(confidence)))
        
        # Risk emoji
        risk = (tip.get("risk_level") or "").lower()
        if "alacsony" in risk or "low" in risk:
            risk_emoji = "🟢"
        elif "közepes" in risk or "medium" in risk:
            risk_emoji = "🟡"
        else:
            risk_emoji = "🔴"
        
        lines.append(f"*{i}. {home} vs {away}*")
        lines.append(f"   🎯 Tipp: *{selection}*")
        lines.append(f"   📊 Odds: *{odds_txt}* | {risk_emoji} | {stars}")
        
        # Liga info (if available)
        league = tip.get("league_name", "")
        time = tip.get("kickoff_local", "")
        if league:
            time_short = time.split("T")[1][:5] if "T" in time else ""
            lines.append(f"   🏆 {league} | ⏰ {time_short}")
        
        lines.append("")
    
    # Combos
    if combos:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🎫 *AJÁNLOTT KOMBÓK*")
        lines.append("")
        
        for j, combo in enumerate(combos[:2], 1):  # Max 2 kombó
            picks = combo.get("picks", [])
            total_odds = combo.get("total_odds")
            if not total_odds or not picks:
                continue
            
            stake = 1000  # Ft
            payout = int(stake * total_odds)
            profit = payout - stake
            
            lines.append(f"*KOMBÓ #{j}* ({len(picks)} meccs)")
            lines.append(f"💰 Odds: *{total_odds:.2f}x*")
            lines.append(f"💵 1000 Ft tét → *{payout} Ft* kifizetés (*+{profit} Ft*)")
            
            # Pick refs
            pick_refs = ", ".join([f"#{p['index']}" for p in picks if 'index' in p])
            if pick_refs:
                lines.append(f"📌 Meccsek: {pick_refs}")
            
            lines.append("")
    
    # Footer
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *Fontos:*")
    lines.append("• Felelősségteljesen fogadj!")
    lines.append("• Csak olyan pénzt használj, amit megengedhetsz magadnak!")
    lines.append("")
    lines.append("🎁 _7 nap INGYEN próba → utána 3.990 Ft/hó_")
    
    message = "\n".join(lines)
    buttons = create_inline_buttons()
    
    return message, buttons


def format_marketing_free(
    tips: List[Dict[str, Any]],
    date_str: str,
) -> tuple[str, List[List[Dict[str, str]]]]:
    """
    Marketing-optimalizált FREE üzenet.
    """
    
    lines = [
        "⚽️ *SZELVÉNYKIRÁLY - Napi Tippek*",
        f"📅 {date_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🆓 *INGYENES TIPPEK*",
        "",
    ]
    
    # Tips (max 3)
    for i, tip in enumerate(tips[:3], 1):
        home = tip.get("home_team", "")
        away = tip.get("away_team", "")
        selection = tip.get("selection", "")
        odds = tip.get("odds_estimate")
        odds_txt = f"{odds:.2f}" if odds else "TBA"
        
        lines.append(f"*{i}. {home} vs {away}*")
        lines.append(f"   🎯 {selection}")
        lines.append(f"   📊 Odds: *{odds_txt}*")
        lines.append("")
    
    # CTA
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💎 *Több tipp kell?*")
    lines.append("")
    lines.append("🎯 VIP tagjaink *naponta 6-12 kiemelt tippet* kapnak")
    lines.append("📊 Élő statisztikák + ROI tracking")
    lines.append("🏆 Profi elemzések sérülésekkel, formával")
    lines.append("")
    lines.append("🎁 *7 nap INGYEN* kipróbálás!")
    
    message = "\n".join(lines)
    buttons = create_inline_buttons()
    
    # Add VIP CTA button to top row
    buttons.insert(0, [
        {"text": "💎 VIP előfizetés (7 nap ingyen)", "url": os.getenv("TIPPMIX_VIP_URL", "https://tippmix.vercel.app/vip")}
    ])
    
    return message, buttons


def format_alert_message(
    tip: Dict[str, Any],
    reason: str = "",
) -> tuple[str, List[List[Dict[str, str]]]]:
    """
    🚨 Alert üzenet (erős tipp azonnal).
    """
    
    home = tip.get("home_team", "")
    away = tip.get("away_team", "")
    selection = tip.get("selection", "")
    odds = tip.get("odds_estimate")
    odds_txt = f"{odds:.2f}" if odds else "TBA"
    confidence = tip.get("confidence", 3.0)
    league = tip.get("league_name", "")
    time = tip.get("kickoff_local", "")
    
    time_short = time.split("T")[1][:5] if "T" in time else ""
    
    lines = [
        "🚨 *ERŐS TIPP ÉSZLELVE!*",
        "",
        f"⚽️ *{home} vs {away}*",
        f"🏆 {league} | ⏰ {time_short}",
        "",
        f"🎯 Tipp: *{selection}*",
        f"📊 Odds: *{odds_txt}*",
        f"⭐ Bizalom: *{confidence:.1f}/5*",
        "",
    ]
    
    if reason:
        lines.append(f"💡 *Miért?*")
        lines.append(f"_{reason}_")
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⏰ *GYORS FOGADÁS AJÁNLOTT!*")
    lines.append("Odds változhat, ne késs!")
    
    message = "\n".join(lines)
    
    # Alert buttons: direct betting link
    buttons = [
        [
            {"text": "⚡ Fogadás most (Tippmix PRO)", "url": "https://www.tippmixpro.hu"},
            {"text": "📊 Részletek", "url": os.getenv("TIPPMIX_DASHBOARD_URL", "https://tippmix.vercel.app")},
        ]
    ]
    
    return message, buttons


def format_weekly_report(
    stats_7d: Dict[str, Any],
    top_wins: List[Dict[str, Any]],
) -> tuple[str, List[List[Dict[str, str]]]]:
    """
    📊 Heti teljesítmény riport.
    """
    
    total_bets = stats_7d.get("total_bets", 0)
    wins = stats_7d.get("wins", 0)
    losses = stats_7d.get("losses", 0)
    win_rate = stats_7d.get("hit_rate", 0)
    roi = stats_7d.get("roi", 0)
    profit = stats_7d.get("profit", 0)
    
    lines = [
        "📊 *HETI TELJESÍTMÉNY RIPORT*",
        "",
        f"📅 Elmúlt 7 nap összesítés",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📈 *EREDMÉNYEK*",
        "",
        f"🎯 Találati arány: *{win_rate:.0f}%* ({wins}/{total_bets})",
        f"💰 ROI: *{roi:+.1f}%*",
        f"💵 Profit: *{profit:+.0f} Ft* (1000 Ft/tipp)",
        "",
    ]
    
    # Top wins
    if top_wins:
        lines.append("🏆 *TOP 3 NYERŐ TIPP*")
        lines.append("")
        
        for i, win in enumerate(top_wins[:3], 1):
            match = win.get("match", "")
            tip = win.get("tip", "")
            odds = win.get("odds", 0)
            
            lines.append(f"{i}. *{match}*")
            lines.append(f"   🎯 {tip} @ {odds:.2f} ✅")
            lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *Következő hét célja:*")
    lines.append(f"Tartsuk a {win_rate:.0f}%+ találati arányt!")
    lines.append("")
    lines.append("🙏 Köszönjük a bizalmat!")
    
    message = "\n".join(lines)
    buttons = create_inline_buttons()
    
    return message, buttons
