import os
import sqlite3
import datetime
from typing import Any, Dict, Optional

from bot.storage.sqlite_store import _db_path  # type: ignore


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def _utc_iso() -> str:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()


def ensure_results_columns() -> None:
    """Best-effort schema migration: add goal + team/league ids to results.

    Keeps existing installs working (SQLite doesn't have IF NOT EXISTS for columns).
    """
    if not os.path.exists(_db_path()):
        return

    cols = {
        "home_goals": "INTEGER",
        "away_goals": "INTEGER",
        "home_team_id": "INTEGER",
        "away_team_id": "INTEGER",
        "league_id": "INTEGER",
        "season": "INTEGER",
    }

    con = _connect()
    try:
        existing = {r["name"] for r in con.execute("PRAGMA table_info(results)").fetchall()}
        for name, ctype in cols.items():
            if name in existing:
                continue
            try:
                con.execute(f"ALTER TABLE results ADD COLUMN {name} {ctype}")
            except Exception:
                pass
        con.commit()
    finally:
        con.close()


def _days_ago(days: int) -> str:
    dt = datetime.date.today() - datetime.timedelta(days=max(0, int(days)))
    return dt.isoformat()


def team_goal_rates(team_id: int, days: int = 120) -> Optional[Dict[str, float]]:
    """Return per-match avg goals for/against for a team over last N days."""
    if not os.path.exists(_db_path()):
        return None

    ensure_results_columns()
    start = _days_ago(days)

    sql = """
      SELECT
        SUM(CASE WHEN home_team_id = ? THEN COALESCE(home_goals, NULL)
                 WHEN away_team_id = ? THEN COALESCE(away_goals, NULL)
                 ELSE NULL END) AS gf_sum,
        SUM(CASE WHEN home_team_id = ? THEN COALESCE(away_goals, NULL)
                 WHEN away_team_id = ? THEN COALESCE(home_goals, NULL)
                 ELSE NULL END) AS ga_sum,
        SUM(CASE WHEN (home_team_id = ? OR away_team_id = ?) AND home_goals IS NOT NULL AND away_goals IS NOT NULL THEN 1 ELSE 0 END) AS n
      FROM results
      WHERE updated_ts_utc >= ?
        AND status IN ('FT','AET','PEN')
    """

    con = _connect()
    try:
        row = con.execute(sql, (team_id, team_id, team_id, team_id, team_id, team_id, start)).fetchone()
        if not row:
            return None
        n = int(row["n"] or 0)
        if n < int(os.getenv("TIPPMIX_TEAM_MIN_N", "8")):
            return None
        gf = float(row["gf_sum"] or 0.0) / n
        ga = float(row["ga_sum"] or 0.0) / n
        return {"n": float(n), "gf": gf, "ga": ga}
    finally:
        con.close()


def league_goal_baseline(league_id: int, days: int = 180) -> Optional[Dict[str, float]]:
    """League baseline goals per match for home/away over last N days."""
    if not os.path.exists(_db_path()):
        return None

    ensure_results_columns()
    start = _days_ago(days)

    sql = """
      SELECT
        SUM(CASE WHEN league_id = ? THEN COALESCE(home_goals, NULL) ELSE NULL END) AS hg_sum,
        SUM(CASE WHEN league_id = ? THEN COALESCE(away_goals, NULL) ELSE NULL END) AS ag_sum,
        SUM(CASE WHEN league_id = ? AND home_goals IS NOT NULL AND away_goals IS NOT NULL THEN 1 ELSE 0 END) AS n
      FROM results
      WHERE updated_ts_utc >= ?
        AND status IN ('FT','AET','PEN')
    """

    con = _connect()
    try:
        row = con.execute(sql, (league_id, league_id, league_id, start)).fetchone()
        if not row:
            return None
        n = int(row["n"] or 0)
        if n < int(os.getenv("TIPPMIX_LEAGUE_MIN_N", "20")):
            return None
        hg = float(row["hg_sum"] or 0.0) / n
        ag = float(row["ag_sum"] or 0.0) / n
        # clamp to sane values
        return {"n": float(n), "home_for": max(0.6, min(2.5, hg)), "away_for": max(0.5, min(2.3, ag))}
    finally:
        con.close()
