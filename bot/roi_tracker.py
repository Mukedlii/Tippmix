"""
bot/roi_tracker.py

ROI Tracking & Weekly Report Generation
- Calculate daily/weekly/monthly ROI
- Track hit rates, profit/loss
- Generate beautiful Telegram reports
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def _connect() -> Optional[sqlite3.Connection]:
    path = _db_path()
    if not os.path.exists(path):
        log.warning(f"DB not found: {path}")
        return None
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


class ROITracker:
    """Calculate ROI and performance metrics."""

    def __init__(self, stake_huf: int = 1000):
        self.stake_huf = stake_huf

    def get_stats(self, days: int = 7, tier: Optional[str] = None) -> Dict:
        """
        Calculate stats for the last N days.
        
        Returns:
        {
            "total_bets": int,
            "wins": int,
            "losses": int,
            "pending": int,
            "hit_rate": float (0-100),
            "total_staked": float,
            "total_returns": float,
            "roi": float (percentage),
            "profit": float,
            "avg_odds": float,
            "best_streak": int,
            "worst_streak": int,
        }
        """
        con = _connect()
        if not con:
            return {}

        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            # Build query
            query = """
                SELECT
                    b.id,
                    b.tier,
                    b.tip,
                    b.odds_pick,
                    r.result_1x2
                FROM bets b
                LEFT JOIN results r ON b.fixture_id = r.fixture_id
                JOIN runs ru ON b.run_id = ru.id
                WHERE ru.run_ts_utc >= ?
            """
            params = [cutoff]

            if tier:
                query += " AND LOWER(b.tier) = LOWER(?)"
                params.append(tier)

            query += " ORDER BY b.kickoff_local DESC"

            rows = con.execute(query, params).fetchall()

            total_bets = len(rows)
            wins = 0
            losses = 0
            pending = 0
            total_staked = 0.0
            total_returns = 0.0
            odds_sum = 0.0
            odds_count = 0

            current_streak = 0
            best_streak = 0
            worst_streak = 0
            temp_streak = 0
            last_was_win = None

            for row in rows:
                tip = row["tip"]
                odds = row["odds_pick"]
                result = row["result_1x2"]

                if not result:
                    pending += 1
                    continue

                total_staked += self.stake_huf

                # Determine win/loss
                won = self._evaluate_tip(tip, result)
                
                if won:
                    wins += 1
                    if odds:
                        total_returns += self.stake_huf * float(odds)
                        odds_sum += float(odds)
                        odds_count += 1
                    
                    # Streak tracking
                    if last_was_win:
                        temp_streak += 1
                    else:
                        temp_streak = 1
                    best_streak = max(best_streak, temp_streak)
                    last_was_win = True
                else:
                    losses += 1
                    
                    # Streak tracking
                    if last_was_win is False:
                        temp_streak -= 1
                    else:
                        temp_streak = -1
                    worst_streak = min(worst_streak, temp_streak)
                    last_was_win = False

            resolved = wins + losses
            hit_rate = (wins / resolved * 100) if resolved > 0 else 0
            roi = ((total_returns - total_staked) / total_staked * 100) if total_staked > 0 else 0
            profit = total_returns - total_staked
            avg_odds = (odds_sum / odds_count) if odds_count > 0 else 0

            return {
                "total_bets": total_bets,
                "wins": wins,
                "losses": losses,
                "pending": pending,
                "hit_rate": round(hit_rate, 1),
                "total_staked": total_staked,
                "total_returns": round(total_returns, 2),
                "roi": round(roi, 1),
                "profit": round(profit, 2),
                "avg_odds": round(avg_odds, 2),
                "best_streak": best_streak,
                "worst_streak": abs(worst_streak),
            }

        except Exception as e:
            log.error(f"get_stats error: {e}")
            return {}
        finally:
            con.close()

    def _evaluate_tip(self, tip: str, result: str) -> bool:
        """Check if a tip was correct."""
        tip_lower = (tip or "").lower()
        result_lower = (result or "").lower()

        if "hazai" in tip_lower or "home" in tip_lower:
            return result_lower == "1"
        elif "döntetlen" in tip_lower or "draw" in tip_lower:
            return result_lower == "x"
        elif "vendég" in tip_lower or "away" in tip_lower:
            return result_lower == "2"
        
        return False

    def get_top_wins(self, days: int = 7, limit: int = 5) -> List[Dict]:
        """Get top winning bets by odds."""
        con = _connect()
        if not con:
            return []

        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            rows = con.execute(
                """
                SELECT
                    b.home_team,
                    b.away_team,
                    b.tip,
                    b.odds_pick,
                    b.kickoff_local,
                    r.result_1x2,
                    r.final_score
                FROM bets b
                JOIN results r ON b.fixture_id = r.fixture_id
                JOIN runs ru ON b.run_id = ru.id
                WHERE ru.run_ts_utc >= ?
                  AND r.result_1x2 IS NOT NULL
                  AND b.odds_pick IS NOT NULL
                ORDER BY b.odds_pick DESC
                LIMIT ?
            """,
                (cutoff, limit),
            ).fetchall()

            wins = []
            for row in rows:
                if self._evaluate_tip(row["tip"], row["result_1x2"]):
                    wins.append({
                        "match": f"{row['home_team']} vs {row['away_team']}",
                        "tip": row["tip"],
                        "odds": row["odds_pick"],
                        "score": row["final_score"],
                        "date": row["kickoff_local"][:10],
                    })

            return wins

        except Exception as e:
            log.error(f"get_top_wins error: {e}")
            return []
        finally:
            con.close()


def generate_weekly_report(lang: str = "hu") -> str:
    """Generate a beautiful weekly performance report for Telegram."""
    
    tracker = ROITracker()
    
    # Get stats for different periods
    weekly = tracker.get_stats(days=7)
    monthly = tracker.get_stats(days=30)
    
    # Get tier-specific stats
    vip_weekly = tracker.get_stats(days=7, tier="VIP")
    free_weekly = tracker.get_stats(days=7, tier="FREE")
    
    # Get top wins
    top_wins = tracker.get_top_wins(days=7, limit=3)
    
    if lang == "en":
        return _format_report_en(weekly, monthly, vip_weekly, free_weekly, top_wins)
    else:
        return _format_report_hu(weekly, monthly, vip_weekly, free_weekly, top_wins)


def _format_report_hu(weekly, monthly, vip_weekly, free_weekly, top_wins) -> str:
    """Format Hungarian report."""
    
    if not weekly:
        return "❌ Nincs elegendő adat a jelentéshez."
    
    # Emoji based on performance
    roi_emoji = "🟢" if weekly["roi"] > 0 else "🔴" if weekly["roi"] < 0 else "🟡"
    trend = "📈" if weekly["roi"] > monthly.get("roi", 0) else "📉"
    
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━",
        "📊 **HETI TELJESÍTMÉNY JELENTÉS**",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "**📅 Elmúlt 7 nap:**",
        f"{roi_emoji} ROI: **{weekly['roi']:+.1f}%** {trend}",
        f"💰 Profit: **{weekly['profit']:+.0f} Ft** (1000 Ft tét/tipp)",
        f"🎯 Találati arány: **{weekly['hit_rate']:.1f}%** ({weekly['wins']}/{weekly['wins'] + weekly['losses']})",
        f"📊 Átlag odds: **{weekly['avg_odds']:.2f}**",
        f"🔥 Legjobb széria: **{weekly['best_streak']} win**",
        f"❄️ Leghosszabb vesztés: **{weekly['worst_streak']} loss**",
        "",
    ]
    
    # Add tier breakdown if available
    if vip_weekly and free_weekly:
        lines.extend([
            "**📦 Tier Breakdown:**",
            f"🌟 VIP: {vip_weekly['hit_rate']:.1f}% ({vip_weekly['wins']}/{vip_weekly['wins'] + vip_weekly['losses']}), ROI: {vip_weekly['roi']:+.1f}%",
            f"🆓 FREE: {free_weekly['hit_rate']:.1f}% ({free_weekly['wins']}/{free_weekly['wins'] + free_weekly['losses']}), ROI: {free_weekly['roi']:+.1f}%",
            "",
        ])
    
    # Monthly comparison
    if monthly:
        lines.extend([
            "**📆 30 napos összehasonlítás:**",
            f"ROI: {monthly['roi']:+.1f}% | Hit rate: {monthly['hit_rate']:.1f}%",
            "",
        ])
    
    # Top wins
    if top_wins:
        lines.extend([
            "**🏆 Top 3 nyerő tipp (odds szerint):**",
        ])
        for i, win in enumerate(top_wins, 1):
            lines.append(f"{i}. {win['match']} → **{win['tip']}** @{win['odds']} ✅")
        lines.append("")
    
    # Call to action
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━",
        "💎 Szeretnél VIP tippeket?",
        "👉 /vip parancs a részletekért",
    ])
    
    return "\n".join(lines)


def _format_report_en(weekly, monthly, vip_weekly, free_weekly, top_wins) -> str:
    """Format English report."""
    
    if not weekly:
        return "❌ Not enough data for report."
    
    roi_emoji = "🟢" if weekly["roi"] > 0 else "🔴" if weekly["roi"] < 0 else "🟡"
    trend = "📈" if weekly["roi"] > monthly.get("roi", 0) else "📉"
    
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━",
        "📊 **WEEKLY PERFORMANCE REPORT**",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "**📅 Last 7 days:**",
        f"{roi_emoji} ROI: **{weekly['roi']:+.1f}%** {trend}",
        f"💰 Profit: **${weekly['profit'] / 300:+.0f}** ($5 stake/tip)",
        f"🎯 Hit rate: **{weekly['hit_rate']:.1f}%** ({weekly['wins']}/{weekly['wins'] + weekly['losses']})",
        f"📊 Avg odds: **{weekly['avg_odds']:.2f}**",
        f"🔥 Best streak: **{weekly['best_streak']} wins**",
        f"❄️ Worst streak: **{weekly['worst_streak']} losses**",
        "",
    ]
    
    if vip_weekly and free_weekly:
        lines.extend([
            "**📦 Tier Breakdown:**",
            f"🌟 VIP: {vip_weekly['hit_rate']:.1f}% ({vip_weekly['wins']}/{vip_weekly['wins'] + vip_weekly['losses']}), ROI: {vip_weekly['roi']:+.1f}%",
            f"🆓 FREE: {free_weekly['hit_rate']:.1f}% ({free_weekly['wins']}/{free_weekly['wins'] + free_weekly['losses']}), ROI: {free_weekly['roi']:+.1f}%",
            "",
        ])
    
    if monthly:
        lines.extend([
            "**📆 30-day comparison:**",
            f"ROI: {monthly['roi']:+.1f}% | Hit rate: {monthly['hit_rate']:.1f}%",
            "",
        ])
    
    if top_wins:
        lines.extend([
            "**🏆 Top 3 wins (by odds):**",
        ])
        for i, win in enumerate(top_wins, 1):
            lines.append(f"{i}. {win['match']} → **{win['tip']}** @{win['odds']} ✅")
        lines.append("")
    
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━",
        "💎 Want VIP tips?",
        "👉 /vip for details",
    ])
    
    return "\n".join(lines)


def send_weekly_report_to_telegram():
    """Send weekly report to Telegram channels."""
    import requests
    from dotenv import load_dotenv
    
    load_dotenv()
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_chat = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")
    vip_chat = os.getenv("TELEGRAM_VIP_CHAT_ID")
    
    if not bot_token:
        log.error("TELEGRAM_BOT_TOKEN not set")
        return
    
    report_hu = generate_weekly_report(lang="hu")
    
    # Send to public channel
    if public_chat:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={
                "chat_id": public_chat,
                "text": report_hu,
                "parse_mode": "Markdown",
            }, timeout=10)
            log.info("Weekly report sent to public channel")
        except Exception as e:
            log.error(f"Failed to send to public: {e}")
    
    # Send to VIP channel
    if vip_chat:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={
                "chat_id": vip_chat,
                "text": report_hu,
                "parse_mode": "Markdown",
            }, timeout=10)
            log.info("Weekly report sent to VIP channel")
        except Exception as e:
            log.error(f"Failed to send to VIP: {e}")
