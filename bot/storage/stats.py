import os
import sqlite3
import datetime
from typing import Dict, List, Tuple, Optional


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def _date_days_ago(days: int) -> str:
    dt = datetime.date.today() - datetime.timedelta(days=max(0, int(days)))
    return dt.isoformat()


def league_hitrate_map(
    days: int = 60,
    min_samples: int = 25,
    tier: Optional[str] = None,
) -> Dict[str, Dict[str, float]]:
    """Returns {league_name: {decided, win, lose, hitrate}} for last N days.

    Joins bets to results on fixture_id and settles only 1X2 with final result_1x2.

    Note: result_1x2 is stored as "1" | "X" | "2".
    tip is stored in HU: "Hazai győzelem" | "Döntetlen" | "Vendég győzelem".
    """

    if not os.path.exists(_db_path()):
        return {}

    start_date = _date_days_ago(days)

    where_tier = "" if not tier else "AND b.tier = ?"
    params: List[str] = [start_date]
    if tier:
        params.append(tier)

    sql = f"""
      SELECT
        COALESCE(NULLIF(TRIM(b.league_name), ''), 'Unknown') AS league,
        SUM(CASE WHEN r.result_1x2 IN ('1','X','2') THEN 1 ELSE 0 END) AS decided,
        SUM(
          CASE
            WHEN r.result_1x2 = '1' AND LOWER(COALESCE(b.tip,'')) LIKE '%hazai%gy%' THEN 1
            WHEN r.result_1x2 = '2' AND LOWER(COALESCE(b.tip,'')) LIKE '%vend%g%y%' THEN 1
            WHEN r.result_1x2 = 'X' AND LOWER(COALESCE(b.tip,'')) LIKE '%d%ntetlen%' THEN 1
            ELSE 0
          END
        ) AS win
      FROM bets b
      JOIN runs ru ON ru.id = b.run_id
      LEFT JOIN results r ON r.fixture_id = b.fixture_id
      WHERE ru.run_date >= ?
        AND b.fixture_id IS NOT NULL
        {where_tier}
      GROUP BY league
    """

    out: Dict[str, Dict[str, float]] = {}
    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
        for row in rows:
            league = str(row["league"])
            decided = int(row["decided"] or 0)
            win = int(row["win"] or 0)
            lose = max(0, decided - win)
            if decided < min_samples:
                continue
            hit = (win / decided) if decided else 0.0
            out[league] = {
                "decided": float(decided),
                "win": float(win),
                "lose": float(lose),
                "hitrate": float(hit),
            }
    finally:
        con.close()

    return out


def overall_hitrate(days: int = 30, tier: Optional[str] = None) -> Optional[Dict[str, float]]:
    """Overall hitrate over last N days from DB results.

    Returns None if DB missing.
    """
    if not os.path.exists(_db_path()):
        return None

    start_date = _date_days_ago(days)
    where_tier = "" if not tier else "AND b.tier = ?"
    params: List[str] = [start_date]
    if tier:
        params.append(tier)

    sql = f"""
      SELECT
        SUM(CASE WHEN r.result_1x2 IN ('1','X','2') THEN 1 ELSE 0 END) AS decided,
        SUM(
          CASE
            WHEN r.result_1x2 = '1' AND LOWER(COALESCE(b.tip,'')) LIKE '%hazai%gy%' THEN 1
            WHEN r.result_1x2 = '2' AND LOWER(COALESCE(b.tip,'')) LIKE '%vend%g%y%' THEN 1
            WHEN r.result_1x2 = 'X' AND LOWER(COALESCE(b.tip,'')) LIKE '%d%ntetlen%' THEN 1
            ELSE 0
          END
        ) AS win
      FROM bets b
      JOIN runs ru ON ru.id = b.run_id
      LEFT JOIN results r ON r.fixture_id = b.fixture_id
      WHERE ru.run_date >= ?
        AND b.fixture_id IS NOT NULL
        {where_tier}
    """

    con = _connect()
    try:
        row = con.execute(sql, params).fetchone()
        decided = int((row["decided"] if row else 0) or 0)
        win = int((row["win"] if row else 0) or 0)
        lose = max(0, decided - win)
        if decided <= 0:
            return {"decided": 0.0, "win": 0.0, "lose": 0.0, "hitrate": 0.0}
        return {"decided": float(decided), "win": float(win), "lose": float(lose), "hitrate": float(win / decided)}
    finally:
        con.close()


def dynamic_block_leagues(
    days: int = 60,
    min_samples: int = 25,
    max_hitrate: float = 0.48,
    tier: Optional[str] = None,
) -> List[str]:
    """Returns leagues to block based on poor historical hitrate."""
    stats = league_hitrate_map(days=days, min_samples=min_samples, tier=tier)
    bad: List[str] = []
    for league, s in stats.items():
        if float(s.get("hitrate", 1.0)) <= max_hitrate:
            bad.append(league)
    # deterministic order: worst first
    bad.sort(key=lambda l: stats[l]["hitrate"])  # type: ignore[index]
    return bad
