"""
bot/roi_display.py

Conditional ROI display based on match completion status.
Prevents showing ROI before today's matches finish.
"""

import sqlite3
import datetime
import os
from typing import Optional, Dict, Any


def has_completed_matches_today(db_path: Optional[str] = None) -> bool:
    """
    Check if today's matches have results in DB.
    
    Returns True if at least one match from today has a result.
    Otherwise returns False (shows "Eredmények később").
    """
    
    if db_path is None:
        db_path = os.getenv("TIPPMIX_DB_PATH", "data/tippmix.db")
    
    if not os.path.exists(db_path):
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        today = datetime.date.today().isoformat()
        
        # Check if any result has a final score
        c.execute("""
            SELECT COUNT(*) FROM results
            WHERE date(kickoff_ts_utc) = ?
            AND (home_goals IS NOT NULL AND away_goals IS NOT NULL)
            LIMIT 1
        """, (today,))
        
        result = c.fetchone()
        conn.close()
        
        return result and result[0] > 0
    
    except Exception as e:
        print(f"[ROI_DISPLAY] DB check failed: {repr(e)}")
        return False


def get_roi_stats_if_ready(
    days: int = 30,
    tier: str = "VIP",
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get ROI stats ONLY if matches have completed today.
    
    Returns:
        {win_rate, roi, profit} if ready
        None if no results yet (placeholder will show instead)
    """
    
    if not has_completed_matches_today(db_path):
        return None
    
    # Get stats
    if db_path is None:
        db_path = os.getenv("TIPPMIX_DB_PATH", "data/tippmix.db")
    
    if not os.path.exists(db_path):
        return None
    
    try:
        from bot.roi_tracker import ROITracker
        tracker = ROITracker(db_path=db_path)
        stats = tracker.get_stats(days=days, tier=tier)
        
        if stats and stats.get("decided", 0) >= 1:  # At least 1 match decided
            return {
                "win_rate": stats.get("hitrate", 0) * 100,
                "roi": stats.get("roi", 0),
                "profit": stats.get("profit", 0),
            }
        
        return None
    
    except Exception as e:
        print(f"[ROI_DISPLAY] Stats fetch failed: {repr(e)}")
        return None


def format_roi_section(
    stats: Optional[Dict[str, Any]],
    show_placeholder: bool = True
) -> str:
    """
    Format ROI section for Telegram message.
    
    Args:
        stats: ROI dict or None
        show_placeholder: Show "Eredmények később" if no stats
    
    Returns:
        Formatted text (or empty string if stats=None and show_placeholder=False)
    """
    
    if stats is None:
        if show_placeholder:
            return "📊 Eredmények később...\n"
        return ""
    
    win_rate = stats.get("win_rate", 0)
    roi = stats.get("roi", 0)
    
    return f"📊 *Teljesítmény (30 nap):* {win_rate:.0f}% találat | ROI: {roi:+.1f}%\n"


def inject_roi_into_vip_message(
    vip_text: str,
    days: int = 30,
    tier: str = "VIP",
    db_path: Optional[str] = None
) -> str:
    """
    Inject ROI stats into VIP message (if ready).
    
    Replaces placeholder or inserts after header.
    """
    
    stats = get_roi_stats_if_ready(days=days, tier=tier, db_path=db_path)
    roi_section = format_roi_section(stats, show_placeholder=True)
    
    # Try to replace placeholder if it exists
    if "Eredmények később" in vip_text:
        return vip_text.replace(
            "📊 Eredmények később...\n",
            roi_section
        )
    
    # Otherwise insert after first line
    lines = vip_text.split("\n")
    if len(lines) > 1:
        lines.insert(2, roi_section.rstrip())
        return "\n".join(lines)
    
    return vip_text
