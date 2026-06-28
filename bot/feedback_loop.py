"""
bot/feedback_loop.py

Daily learning system:
1. Fetch completed matches (results table)
2. Find matching bets we made
3. Calculate hit/miss
4. Retrain ML model with new data
5. Update confidence weights

Runs daily after matches complete (evening)
"""

import os
import logging
import sqlite3
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
import json

log = logging.getLogger(__name__)

try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


class FeedbackLoop:
    """Daily retraining system."""
    
    def __init__(self, db_path: Optional[str] = None, model_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("TIPPMIX_DB_PATH", "data/tippmix.db")
        self.model_path = model_path or os.getenv("TIPPMIX_ML_MODEL_PATH", "data/ml_model.pkl")
        self._ensure_tables()
    
    def _ensure_tables(self) -> None:
        """Ensure feedback tables exist."""
        
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Bets table (if not exists)
            c.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY,
                    run_date TEXT,
                    slot TEXT,
                    league_name TEXT,
                    home_team TEXT,
                    away_team TEXT,
                    tip TEXT,
                    odds_pick REAL,
                    confidence REAL,
                    tier TEXT,
                    fixture_id TEXT,
                    result TEXT,
                    result_correct INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Results table (if not exists)
            c.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY,
                    home_team TEXT,
                    away_team TEXT,
                    home_goals INTEGER,
                    away_goals INTEGER,
                    kickoff_ts_utc TEXT,
                    source TEXT,
                    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(home_team, away_team, kickoff_ts_utc)
                )
            """)
            
            # Feedback log
            c.execute("""
                CREATE TABLE IF NOT EXISTS feedback_log (
                    id INTEGER PRIMARY KEY,
                    feedback_date TEXT,
                    bets_matched INTEGER,
                    bets_correct INTEGER,
                    hitrate REAL,
                    model_retrained INTEGER,
                    stats JSON,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            conn.close()
            log.info("[FEEDBACK] Tables ensured")
        
        except Exception as e:
            log.error(f"[FEEDBACK] Table creation error: {repr(e)}")
    
    def match_bets_with_results(self) -> Tuple[int, int, List[Dict[str, Any]]]:
        """
        Match completed bets with final results.
        
        Returns:
            (total_matched, correct_picks, matched_records)
        """
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Get unresolved bets (from last 3 days)
            cutoff = (datetime.now() - timedelta(days=3)).isoformat()
            
            c.execute("""
                SELECT 
                    b.id,
                    b.home_team,
                    b.away_team,
                    b.tip,
                    b.confidence,
                    b.league_name,
                    b.fixture_id,
                    b.created_at,
                    r.home_goals,
                    r.away_goals
                FROM bets b
                LEFT JOIN results r ON (
                    LOWER(b.home_team) = LOWER(r.home_team)
                    AND LOWER(b.away_team) = LOWER(r.away_team)
                )
                WHERE b.result IS NULL
                  AND b.created_at >= ?
                  AND r.home_goals IS NOT NULL
                ORDER BY b.created_at DESC
            """, (cutoff,))
            
            matches = c.fetchall()
            
            matched_records = []
            correct_count = 0
            
            for m in matches:
                result = self._evaluate_bet(
                    tip=m["tip"],
                    home_goals=m["home_goals"],
                    away_goals=m["away_goals"]
                )
                
                is_correct = 1 if result else 0
                correct_count += is_correct
                
                # Update bet
                c.execute("""
                    UPDATE bets
                    SET result = ?, result_correct = ?
                    WHERE id = ?
                """, (result, is_correct, m["id"]))
                
                matched_records.append({
                    "bet_id": m["id"],
                    "home_team": m["home_team"],
                    "away_team": m["away_team"],
                    "tip": m["tip"],
                    "confidence": m["confidence"],
                    "league_name": m["league_name"],
                    "home_goals": m["home_goals"],
                    "away_goals": m["away_goals"],
                    "result": result,
                    "correct": is_correct,
                })
            
            conn.commit()
            conn.close()
            
            total = len(matches)
            log.info(f"[FEEDBACK] Matched {total} bets, {correct_count} correct ({100*correct_count/total if total > 0 else 0:.1f}%)")
            
            return total, correct_count, matched_records
        
        except Exception as e:
            log.error(f"[FEEDBACK] Match error: {repr(e)}")
            return 0, 0, []
    
    def _evaluate_bet(self, tip: str, home_goals: int, away_goals: int) -> Optional[str]:
        """
        Evaluate if bet won.
        
        Args:
            tip: "Hazai győzelem", "Döntetlen", "Vendég győzelem"
            home_goals: Final home score
            away_goals: Final away score
        
        Returns:
            Tip if correct, None if wrong
        """
        
        try:
            tip_lower = str(tip or "").lower().strip()
            
            if "hazai" in tip_lower or "home" in tip_lower:
                result = "1" if home_goals > away_goals else None
            elif "döntetlen" in tip_lower or "draw" in tip_lower or "x" in tip_lower:
                result = "X" if home_goals == away_goals else None
            elif "vendég" in tip_lower or "away" in tip_lower:
                result = "2" if away_goals > home_goals else None
            else:
                result = None
            
            return result
        
        except Exception:
            return None
    
    def log_feedback(
        self,
        total_matched: int,
        correct_count: int,
        model_retrained: bool = False,
        extra_stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Log feedback session to DB."""
        
        try:
            hitrate = (correct_count / total_matched) if total_matched > 0 else 0
            
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute("""
                INSERT INTO feedback_log
                (feedback_date, bets_matched, bets_correct, hitrate, model_retrained, stats)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                date.today().isoformat(),
                total_matched,
                correct_count,
                hitrate,
                1 if model_retrained else 0,
                json.dumps(extra_stats or {}, default=str),
            ))
            
            conn.commit()
            conn.close()
            
            log.info(f"[FEEDBACK] Logged: {total_matched} bets, {correct_count} correct, hitrate={hitrate:.1%}")
            return True
        
        except Exception as e:
            log.error(f"[FEEDBACK] Log error: {repr(e)}")
            return False
    
    def get_league_stats(self, days: int = 30) -> Dict[str, Dict[str, Any]]:
        """
        Get league performance stats.
        
        Returns:
            {league_name: {total, correct, hitrate}}
        """
        
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            
            c.execute("""
                SELECT 
                    league_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN result_correct = 1 THEN 1 ELSE 0 END) as correct
                FROM bets
                WHERE result_correct IS NOT NULL
                  AND created_at >= ?
                GROUP BY league_name
                ORDER BY total DESC
            """, (cutoff,))
            
            stats = {}
            for league, total, correct in c.fetchall():
                stats[league] = {
                    "total": total,
                    "correct": correct or 0,
                    "hitrate": (correct or 0) / total if total > 0 else 0,
                }
            
            conn.close()
            return stats
        
        except Exception as e:
            log.error(f"[FEEDBACK] Stats error: {repr(e)}")
            return {}
    
    async def run_daily_feedback(self) -> Dict[str, Any]:
        """
        Run complete daily feedback loop.
        
        Returns:
            {total_matched, correct, hitrate, model_retrained}
        """
        
        log.info("[FEEDBACK] Starting daily feedback loop...")
        
        # 1. Match bets with results
        total, correct, records = self.match_bets_with_results()
        
        if total == 0:
            log.info("[FEEDBACK] No new results to process")
            return {"total_matched": 0, "correct": 0, "hitrate": 0, "model_retrained": False}
        
        hitrate = correct / total
        
        # 2. Get league stats for logging
        league_stats = self.get_league_stats(days=30)
        
        # 3. Log feedback
        self.log_feedback(total, correct, model_retrained=False, extra_stats=league_stats)
        
        # 4. (Optional) Retrain model
        # NOTE: Full retraining happens separately in scheduled job
        
        log.info(f"[FEEDBACK] Complete: {total} matched, {correct} correct, {hitrate:.1%} hitrate")
        
        return {
            "total_matched": total,
            "correct": correct,
            "hitrate": hitrate,
            "records": records,
            "league_stats": league_stats,
            "model_retrained": False,
        }


# Usage:
#
# import asyncio
# from bot.feedback_loop import FeedbackLoop
#
# loop = FeedbackLoop()
# result = asyncio.run(loop.run_daily_feedback())
# print(result)
