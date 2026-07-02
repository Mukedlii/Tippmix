"""
bot/telegram_marketing.py

Marketing-optimalizált Telegram üzenetek + inline gombok.
Hasonló formátum mint a profi tippmix botoknál.
"""

from typing import List, Dict, Any, Optional, Tuple
import os

MAX_FORM_RESULTS = 3


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
    
    lines = ["⚽ VIP TIPPEK", "━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if date_str:
        lines.append(f"Dátum: {date_str}")
    if stats:
        try:
            lines.append(f"Forma: {float(stats.get('win_rate', 0)):.0f}% | ROI {float(stats.get('roi', 0)):+.1f}%")
        except Exception:
            pass

    for i, tip in enumerate(tips, 1):
        home = tip.get("home_team") or ""
        away = tip.get("away_team") or ""
        selection = tip.get("selection") or tip.get("tip") or ""
        odds_txt, bookmaker = _best_odds_and_bookmaker(tip)
        conf = _safe_confidence(tip.get("confidence"))
        home_form = _compact_form(tip.get("home_form"))
        away_form = _compact_form(tip.get("away_form"))

        lines.append("")
        lines.append(f"{i}. {home} vs {away}")
        lines.append(f"   Pick: {selection} | {odds_txt} ({bookmaker})")
        lines.append(f"   Form: {home_form} vs {away_form} | Conf: {conf:.1f}/5")

    if combos:
        lines.append("")
        lines.append("💎 KOMBINÁCIÓK")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
        for j, combo in enumerate(combos[:2], 1):
            total_odds = combo.get("total_odds")
            picks = combo.get("picks") or []
            if not picks or not total_odds:
                continue
            label = combo.get("label") or _combo_label(picks)
            lines.append(f"Kombi {j}: {label} | {float(total_odds):.2f} odds")
    
    message = "\n".join(lines)
    buttons = create_inline_buttons()
    
    return message, buttons


def format_marketing_free(
    tips: List[Dict[str, Any]],
    combos: List[Dict[str, Any]],
    date_str: str,
) -> tuple[str, List[List[Dict[str, str]]]]:
    """
    Marketing-optimalizált FREE üzenet.
    """
    
    lines = ["⚽ FREE TIPPEK", "━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if date_str:
        lines.append(f"Dátum: {date_str}")

    for i, tip in enumerate(tips, 1):
        home = tip.get("home_team") or ""
        away = tip.get("away_team") or ""
        selection = tip.get("selection") or tip.get("tip") or ""
        odds_txt, bookmaker = _best_odds_and_bookmaker(tip)
        lines.append("")
        lines.append(f"{i}. {home} vs {away}")
        lines.append(f"   Pick: {selection} | {odds_txt} ({bookmaker})")

    if combos:
        lines.append("")
        lines.append("🔗 KETTŐS")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
        for combo in combos[:2]:
            total_odds = combo.get("total_odds")
            picks = combo.get("picks") or []
            if not picks or not total_odds:
                continue
            label = combo.get("label") or _combo_label(picks)
            lines.append(f"{label} | {float(total_odds):.2f} odds")
    
    message = "\n".join(lines)
    buttons = create_inline_buttons()
    
    return message, buttons


def _safe_confidence(raw: Any) -> float:
    try:
        return float(raw)
    except Exception:
        return 0.0


def _best_odds_and_bookmaker(tip: Dict[str, Any]) -> Tuple[str, str]:
    odds = tip.get("best_odds") or tip.get("odds_pick") or tip.get("odds_estimate")
    bookmaker = tip.get("bookmaker") or tip.get("best_bookmaker") or "N/A"
    try:
        return f"{float(odds):.2f}", str(bookmaker)
    except Exception:
        return "TBA", str(bookmaker)


def _compact_form(raw_form: Any) -> str:
    if not raw_form:
        return "➖➖➖"
    if isinstance(raw_form, str):
        vals = list(raw_form[:MAX_FORM_RESULTS])
    elif isinstance(raw_form, list):
        vals = [str(v)[:1] for v in raw_form[:MAX_FORM_RESULTS]]
    else:
        return "➖➖➖"
    out = []
    for v in vals:
        u = str(v).upper()
        if u == "W":
            out.append("✅")
        elif u == "L":
            out.append("❌")
        else:
            out.append("➖")
    while len(out) < MAX_FORM_RESULTS:
        out.append("➖")
    return "".join(out)


def _combo_label(picks: List[Dict[str, Any]]) -> str:
    bits = []
    for p in picks:
        team = p.get("home_team") or p.get("match") or "Tip"
        sel = p.get("selection") or p.get("tip") or ""
        if sel == "Hazai győzelem":
            sel = "H"
        elif sel == "Vendég győzelem":
            sel = "V"
        elif sel == "Döntetlen":
            sel = "X"
        bits.append(f"{team} {sel}".strip())
    return " + ".join(bits)


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
    odds_txt, bookmaker = _best_odds_and_bookmaker(tip)
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
        f"📊 Odds: *{odds_txt}* ({bookmaker})",
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
