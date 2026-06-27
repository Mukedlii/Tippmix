"""
bot/telegram_pro_format.py

Clean, professional Telegram format for VIP & FREE tippek.
- Minimum 6 VIP tips, 3 FREE tips (only PRO leagues)
- No exotic leagues, no "n/a" odds, no waste text
- Sharp, mobile-friendly format
"""

import os
from typing import List, Dict, Any, Optional


def _clean_team_name(name: str) -> str:
    """Truncate long team names for mobile readability."""
    name = str(name or "").strip()
    if len(name) > 20:
        return name[:17] + "..."
    return name


def _format_time(kickoff: str) -> str:
    """Extract HH:MM from ISO datetime."""
    try:
        if "T" in kickoff:
            time_part = kickoff.split("T")[1][:5]
            return time_part
    except Exception:
        pass
    return ""


def _format_odds(odds: Optional[float]) -> str:
    """Format odds or show Poisson estimate."""
    if odds is None or odds == 0:
        return "?"
    try:
        o = float(odds)
        if o < 1.01:
            return "?"
        return f"{o:.2f}".rstrip('0').rstrip('.')
    except Exception:
        return "?"


def _confidence_stars(confidence: float) -> str:
    """Convert 0-5 confidence to stars."""
    try:
        c = float(confidence or 0)
        stars = int(c * 1.2)  # 0-5 → 0-6 stars
        return "⭐" * min(5, max(0, stars))
    except Exception:
        return "⭐⭐⭐"


def _risk_emoji(risk_level: str) -> str:
    """Risk level to emoji."""
    risk = (risk_level or "").lower()
    if "alacsony" in risk or "low" in risk:
        return "🟢"
    if "közepes" in risk or "medium" in risk:
        return "🟡"
    return "🔴"


def format_single_tip(
    idx: int,
    tip: Dict[str, Any],
    compact: bool = False
) -> str:
    """
    Format single tip for Telegram.
    
    Args:
        idx: Tip number (1, 2, 3...)
        tip: Bet dict from Poisson engine
        compact: If True, minimal format (for FREE)
    
    Returns:
        Formatted tip string
    """
    
    home = _clean_team_name(tip.get("home_team", "?"))
    away = _clean_team_name(tip.get("away_team", "?"))
    pick = tip.get("tip") or tip.get("pick") or tip.get("selection") or "?"
    odds = _format_odds(tip.get("odds_estimate") or tip.get("odds_pick"))
    confidence = tip.get("confidence", 3.0)
    risk = tip.get("risk_level", "unknown")
    kickoff = tip.get("kickoff_local", "")
    time_str = _format_time(kickoff)
    league = tip.get("league_name", "")
    
    if compact:
        # COMPACT (FREE format - 2 lines per tip)
        return f"{idx}. {home} vs {away}\n   🎯 {pick} @ {odds} {_risk_emoji(risk)}"
    
    # FULL (VIP format - 4 lines per tip)
    lines = [
        f"{idx}. {home} 🆚 {away}",
        f"   ⏰ {time_str} | {league}",
        f"   🎯 {pick} @ {odds} | {_risk_emoji(risk)} | {_confidence_stars(confidence)}",
    ]
    return "\n".join(lines)


def format_vip_message(
    tips: List[Dict[str, Any]],
    date_str: str = ""
) -> str:
    """
    Format VIP message (6+ tips, PRO leagues only).
    
    Requirements:
    - Minimum 6 tips
    - Only Premier, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, etc.
    - All odds present (no "n/a")
    - Sharp formatting
    
    Args:
        tips: List of bet dicts (sorted by confidence)
        date_str: Date string (YYYY.MM.DD.)
    
    Returns:
        Formatted Telegram message
    """
    
    if not tips:
        return "⚠️ Nincs elég PRO tipp ma."
    
    # Take max 12 tips (6+ min)
    tips = tips[:12]
    
    lines = [
        "👑⚽️ SZELVÉNYKIRÁLY VIP",
        f"📅 {date_str or '2026.06.27'}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    
    # Count by confidence tier
    safe_count = len([t for t in tips if (t.get("shelf") or "").upper() == "SAFE"])
    risk_count = len(tips) - safe_count
    
    if safe_count > 0:
        lines.append(f"🟢 SAFE PICKS ({safe_count})")
        lines.append("")
        for i, tip in enumerate([t for t in tips if (t.get("shelf") or "").upper() == "SAFE"][:6], 1):
            lines.append(format_single_tip(i, tip, compact=False))
            lines.append("")
    
    if risk_count > 0:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🟠 HIGH CONFIDENCE ({risk_count})")
        lines.append("")
        for i, tip in enumerate([t for t in tips if (t.get("shelf") or "").upper() != "SAFE"][:6], safe_count + 1):
            lines.append(format_single_tip(i, tip, compact=False))
            lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ Felelősen fogadj!")
    lines.append("💎 VIP: 7 nap INGYEN")
    
    return "\n".join(lines).strip()


def format_free_message(
    tips: List[Dict[str, Any]],
    date_str: str = ""
) -> str:
    """
    Format FREE message (3 tips, compact, PRO leagues only).
    
    Requirements:
    - Exactly 3 tips (best picks)
    - Only Premier, La Liga, Bundesliga, Serie A, Ligue 1
    - All odds present
    - VERY compact (fits 1 screen)
    - Strong CTA for VIP
    
    Args:
        tips: List of bet dicts (sorted by confidence, top 3)
        date_str: Date string
    
    Returns:
        Formatted Telegram message
    """
    
    if not tips:
        return "⚠️ Nincs elég PRO tipp ma."
    
    # Take exactly 3 tips
    tips = tips[:3]
    
    lines = [
        "⚽️ SZELVÉNYKIRÁLY - NAPI TIPPEK",
        f"📅 {date_str or '2026.06.27'}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🆓 INGYENES TIPPEK",
        "",
    ]
    
    for i, tip in enumerate(tips, 1):
        lines.append(format_single_tip(i, tip, compact=True))
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💎 6+ tipp a VIP-ben")
    lines.append("✅ Profi elemzés + odds")
    lines.append("🎁 7 nap INGYEN")
    lines.append("")
    lines.append("⚠️ Felelősen fogadj!")
    
    return "\n".join(lines).strip()


def create_inline_buttons_pro() -> List[List[Dict[str, str]]]:
    """Create inline buttons for PRO messages."""
    
    vip_url = os.getenv("TIPPMIX_VIP_URL", "https://tippmix.vercel.app/vip")
    dashboard_url = os.getenv("TIPPMIX_DASHBOARD_URL", "https://tippmix.vercel.app")
    
    return [
        [
            {"text": "💎 VIP (7 nap ingyen)", "url": vip_url},
            {"text": "📊 Statisztika", "url": dashboard_url},
        ]
    ]


def validate_tips_for_free(tips: List[Dict[str, Any]]) -> bool:
    """
    Validate if we have 3+ PRO league tips for FREE message.
    
    Returns:
        True if valid (3+ tips with odds + PRO league)
        False otherwise
    """
    
    from bot.deduplication import _is_pro_league
    
    if len(tips) < 3:
        return False
    
    valid_tips = 0
    for tip in tips[:3]:
        league = str(tip.get("league_name") or "")
        odds = tip.get("odds_estimate") or tip.get("odds_pick")
        
        # Must be PRO league AND have odds
        if _is_pro_league(league) and odds and float(odds) > 1.01:
            valid_tips += 1
    
    return valid_tips >= 3


def validate_tips_for_vip(tips: List[Dict[str, Any]]) -> bool:
    """
    Validate if we have 6+ PRO league tips for VIP message.
    
    Returns:
        True if valid (6+ tips with odds + PRO league)
        False otherwise
    """
    
    from bot.deduplication import _is_pro_league
    
    if len(tips) < 6:
        return False
    
    valid_tips = 0
    for tip in tips[:12]:
        league = str(tip.get("league_name") or "")
        odds = tip.get("odds_estimate") or tip.get("odds_pick")
        
        # Must be PRO league AND have odds
        if _is_pro_league(league) and odds and float(odds) > 1.01:
            valid_tips += 1
    
    return valid_tips >= 6
