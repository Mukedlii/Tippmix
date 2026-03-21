#!/usr/bin/env python3
"""
Tipster Tracking Database Schema & Functions

Manages:
- Tipster registration & stats
- Tip storage & result tracking
- AI consensus decisions
- Combo bets

Schema created for SQLite (tippmix.db)
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "tippmix.db"
)


def get_db() -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Dict-like access
    return conn


def init_tipster_schema():
    """
    Initialize tipster tracking schema
    Run this ONCE to create tables
    """
    
    conn = get_db()
    c = conn.cursor()
    
    # 1. Tipsters table
    c.execute("""
        CREATE TABLE IF NOT EXISTS tipsters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            source_identifier TEXT,
            
            total_tips INTEGER DEFAULT 0,
            total_settled INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            win_rate REAL,
            total_roi REAL DEFAULT 0.0,
            avg_roi REAL,
            
            is_verified BOOLEAN DEFAULT 0,
            min_sample_reached BOOLEAN DEFAULT 0,
            is_qualified BOOLEAN DEFAULT 0,
            
            first_tip_at TEXT,
            last_tip_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(name, source, source_identifier)
        )
    """)
    
    c.execute("CREATE INDEX IF NOT EXISTS idx_tipsters_qualified ON tipsters(is_qualified)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tipsters_source ON tipsters(source)")
    
    # 2. Tipster tips table
    c.execute("""
        CREATE TABLE IF NOT EXISTS tipster_tips (
            id INTEGER PRIMARY KEY,
            tipster_id INTEGER NOT NULL,
            
            match_date TEXT NOT NULL,
            match_time TEXT,
            league TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            
            selection TEXT NOT NULL,
            selection_display TEXT,
            odds REAL,
            confidence INTEGER,
            
            raw_text TEXT,
            source_url TEXT,
            
            is_settled BOOLEAN DEFAULT 0,
            won BOOLEAN,
            actual_score TEXT,
            settled_at TEXT,
            roi REAL,
            
            scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (tipster_id) REFERENCES tipsters(id)
        )
    """)
    
    c.execute("CREATE INDEX IF NOT EXISTS idx_tipster_tips_match ON tipster_tips(match_date, home_team, away_team)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tipster_tips_tipster ON tipster_tips(tipster_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tipster_tips_settled ON tipster_tips(is_settled)")
    
    # 3. AI consensus table
    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_consensus (
            id INTEGER PRIMARY KEY,
            analysis_date TEXT NOT NULL,
            analysis_run_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            match_date TEXT NOT NULL,
            match_time TEXT,
            league TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            
            selection TEXT NOT NULL,
            selection_display TEXT,
            recommended_odds REAL,
            
            tipster_count INTEGER,
            qualified_tipster_count INTEGER,
            avg_tipster_roi REAL,
            avg_tipster_winrate REAL,
            consensus_strength REAL,
            
            ai_confidence REAL,
            ai_reasoning TEXT,
            
            similar_cases_count INTEGER,
            similar_cases_winrate REAL,
            
            is_top6 BOOLEAN DEFAULT 0,
            rank_position INTEGER,
            
            is_settled BOOLEAN DEFAULT 0,
            won BOOLEAN,
            actual_score TEXT,
            settled_at TEXT,
            roi REAL
        )
    """)
    
    c.execute("CREATE INDEX IF NOT EXISTS idx_ai_consensus_date ON ai_consensus(analysis_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ai_consensus_top6 ON ai_consensus(is_top6)")
    
    # 4. Combo bets table
    c.execute("""
        CREATE TABLE IF NOT EXISTS combo_bets (
            id INTEGER PRIMARY KEY,
            analysis_date TEXT NOT NULL,
            
            combo_size INTEGER NOT NULL,
            combo_type TEXT,
            
            matches_json TEXT NOT NULL,
            
            total_odds REAL NOT NULL,
            
            ai_confidence REAL,
            ai_reasoning TEXT,
            
            is_settled BOOLEAN DEFAULT 0,
            won BOOLEAN,
            settled_count INTEGER DEFAULT 0,
            won_count INTEGER DEFAULT 0,
            roi REAL,
            settled_at TEXT,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ Tipster tracking schema initialized!")


# === TIPSTER FUNCTIONS ===

def register_tipster(name: str, source: str, source_identifier: str = None) -> int:
    """
    Register a new tipster or get existing ID
    
    Returns:
        Tipster ID
    """
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if exists
    c.execute("""
        SELECT id FROM tipsters 
        WHERE name = ? AND source = ? AND (source_identifier = ? OR (source_identifier IS NULL AND ? IS NULL))
    """, (name, source, source_identifier, source_identifier))
    
    row = c.fetchone()
    
    if row:
        conn.close()
        return row['id']
    
    # Insert new
    c.execute("""
        INSERT INTO tipsters (name, source, source_identifier, first_tip_at)
        VALUES (?, ?, ?, ?)
    """, (name, source, source_identifier, datetime.now().isoformat()))
    
    tipster_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return tipster_id


def add_tip(
    tipster_id: int,
    match_date: str,
    home_team: str,
    away_team: str,
    selection: str,
    odds: float = None,
    **kwargs
) -> int:
    """
    Add a tip from a tipster
    
    Returns:
        Tip ID
    """
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        INSERT INTO tipster_tips (
            tipster_id, match_date, home_team, away_team,
            selection, selection_display, odds, confidence,
            match_time, league, raw_text, source_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tipster_id, match_date, home_team, away_team,
        selection, kwargs.get('selection_display'), odds, kwargs.get('confidence'),
        kwargs.get('match_time'), kwargs.get('league'), kwargs.get('raw_text'), kwargs.get('source_url')
    ))
    
    tip_id = c.lastrowid
    
    # Update tipster stats
    c.execute("""
        UPDATE tipsters SET
            total_tips = total_tips + 1,
            last_tip_at = ?,
            updated_at = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), datetime.now().isoformat(), tipster_id))
    
    conn.commit()
    conn.close()
    
    return tip_id


def settle_tip(tip_id: int, won: bool, actual_score: str = None):
    """
    Mark a tip as settled with result
    """
    
    conn = get_db()
    c = conn.cursor()
    
    # Get tip info
    c.execute("SELECT tipster_id, odds FROM tipster_tips WHERE id = ?", (tip_id,))
    tip = c.fetchone()
    
    if not tip:
        conn.close()
        return
    
    tipster_id = tip['tipster_id']
    odds = tip['odds'] or 0
    
    # Calculate ROI
    roi = (odds - 1.0) if won else -1.0
    
    # Update tip
    c.execute("""
        UPDATE tipster_tips SET
            is_settled = 1,
            won = ?,
            actual_score = ?,
            settled_at = ?,
            roi = ?
        WHERE id = ?
    """, (won, actual_score, datetime.now().isoformat(), roi, tip_id))
    
    # Update tipster stats
    c.execute("""
        UPDATE tipsters SET
            total_settled = total_settled + 1,
            total_won = total_won + ?,
            total_roi = total_roi + ?,
            win_rate = CAST(total_won + ? AS REAL) / (total_settled + 1),
            avg_roi = (total_roi + ?) / (total_settled + 1),
            min_sample_reached = CASE WHEN (total_settled + 1) >= 20 THEN 1 ELSE 0 END,
            updated_at = ?
        WHERE id = ?
    """, (
        1 if won else 0,
        roi,
        1 if won else 0,
        roi,
        datetime.now().isoformat(),
        tipster_id
    ))
    
    # Update qualification status
    c.execute("""
        UPDATE tipsters SET
            is_qualified = CASE
                WHEN min_sample_reached = 1 
                AND win_rate >= 0.55 
                AND avg_roi >= 0.05
                THEN 1 ELSE 0
            END
        WHERE id = ?
    """, (tipster_id,))
    
    conn.commit()
    conn.close()


def get_qualified_tipsters() -> List[Dict]:
    """Get all qualified tipsters"""
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM tipsters
        WHERE is_qualified = 1
        ORDER BY avg_roi DESC
    """)
    
    tipsters = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return tipsters


def get_today_tips(match_date: str = None) -> List[Dict]:
    """Get all tips for a specific date"""
    
    if not match_date:
        match_date = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT tt.*, t.name as tipster_name, t.win_rate, t.avg_roi, t.is_qualified
        FROM tipster_tips tt
        JOIN tipsters t ON tt.tipster_id = t.id
        WHERE tt.match_date = ?
        AND tt.is_settled = 0
        ORDER BY t.is_qualified DESC, t.avg_roi DESC
    """, (match_date,))
    
    tips = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return tips


# === AI CONSENSUS FUNCTIONS ===

def save_ai_consensus(
    match_date: str,
    home_team: str,
    away_team: str,
    selection: str,
    ai_confidence: float,
    **kwargs
) -> int:
    """Save AI consensus decision"""
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        INSERT INTO ai_consensus (
            analysis_date, match_date, home_team, away_team,
            selection, selection_display, recommended_odds,
            tipster_count, qualified_tipster_count,
            avg_tipster_roi, avg_tipster_winrate, consensus_strength,
            ai_confidence, ai_reasoning,
            similar_cases_count, similar_cases_winrate,
            is_top6, rank_position,
            match_time, league
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        kwargs.get('analysis_date', datetime.now().strftime("%Y-%m-%d")),
        match_date, home_team, away_team,
        selection, kwargs.get('selection_display'), kwargs.get('recommended_odds'),
        kwargs.get('tipster_count'), kwargs.get('qualified_tipster_count'),
        kwargs.get('avg_tipster_roi'), kwargs.get('avg_tipster_winrate'), kwargs.get('consensus_strength'),
        ai_confidence, kwargs.get('ai_reasoning'),
        kwargs.get('similar_cases_count'), kwargs.get('similar_cases_winrate'),
        kwargs.get('is_top6', 0), kwargs.get('rank_position'),
        kwargs.get('match_time'), kwargs.get('league')
    ))
    
    consensus_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return consensus_id


def get_top6_consensus(analysis_date: str = None) -> List[Dict]:
    """Get today's TOP 6 AI consensus picks"""
    
    if not analysis_date:
        analysis_date = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM ai_consensus
        WHERE analysis_date = ?
        AND is_top6 = 1
        ORDER BY rank_position ASC
    """, (analysis_date,))
    
    picks = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return picks


# Initialize on import (safe, only creates if not exists)
if __name__ == "__main__":
    init_tipster_schema()
    print("\n✅ Schema ready!")
    print(f"📂 Database: {DB_PATH}")
