import os
import json
import sqlite3
import datetime
from typing import Any, Dict, List, Optional


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    _ensure_parent(path)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def init_db() -> None:
    con = _connect()
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_ts_utc TEXT NOT NULL,
              run_date TEXT NOT NULL,
              slot TEXT NOT NULL,
              provider TEXT,
              matches_total INTEGER,
              matches_slot INTEGER,
              vip_count INTEGER,
              public_count INTEGER,
              meta_json TEXT
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS bets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              tier TEXT NOT NULL,               -- VIP / FREE
              fixture_id INTEGER,
              match_key TEXT,
              league_name TEXT,
              country_name TEXT,
              kickoff_local TEXT,
              home_team TEXT,
              away_team TEXT,
              tip TEXT,
              odds_pick REAL,
              odds_1 REAL,
              odds_x REAL,
              odds_2 REAL,
              confidence REAL,
              risk_level TEXT,
              is_highlighted INTEGER,
              reason TEXT,
              raw_json TEXT,
              FOREIGN KEY(run_id) REFERENCES runs(id)
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fixture_id INTEGER NOT NULL,
              final_score TEXT,
              result_1x2 TEXT,
              status TEXT,
              updated_ts_utc TEXT NOT NULL,
              raw_json TEXT
            );
            """
        )
        # One row per fixture_id (latest result snapshot)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_results_fixture_id ON results(fixture_id);")
        con.commit()
    finally:
        con.close()


def _utc_iso() -> str:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()


def insert_run(
    run_date: str,
    slot: str,
    provider: Optional[str],
    matches_total: int,
    matches_slot: int,
    vip_count: int,
    public_count: int,
    meta: Optional[Dict[str, Any]] = None,
) -> int:
    init_db()
    con = _connect()
    try:
        cur = con.execute(
            """
            INSERT INTO runs(run_ts_utc, run_date, slot, provider, matches_total, matches_slot, vip_count, public_count, meta_json)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                _utc_iso(),
                str(run_date),
                str(slot),
                str(provider) if provider else None,
                int(matches_total),
                int(matches_slot),
                int(vip_count),
                int(public_count),
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def insert_bets(run_id: int, tier: str, bets: List[Dict[str, Any]]) -> None:
    if not bets:
        return

    init_db()
    con = _connect()
    try:
        for b in bets:
            odds = b.get("odds_1x2") or {}
            con.execute(
                """
                INSERT INTO bets(
                  run_id, tier, fixture_id, match_key, league_name, country_name, kickoff_local,
                  home_team, away_team, tip,
                  odds_pick, odds_1, odds_x, odds_2,
                  confidence, risk_level, is_highlighted, reason, raw_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(run_id),
                    str(tier),
                    int(b.get("fixture_id")) if b.get("fixture_id") is not None else None,
                    b.get("match_key"),
                    b.get("league_name"),
                    b.get("country_name"),
                    b.get("kickoff_local"),
                    b.get("home_team"),
                    b.get("away_team"),
                    b.get("tip") or b.get("selection") or b.get("pick"),
                    float(b.get("odds_pick")) if b.get("odds_pick") is not None else None,
                    float(odds.get("1")) if odds.get("1") is not None else None,
                    float(odds.get("X")) if odds.get("X") is not None else None,
                    float(odds.get("2")) if odds.get("2") is not None else None,
                    float(b.get("confidence")) if b.get("confidence") is not None else None,
                    b.get("risk_level"),
                    1 if b.get("is_highlighted") else 0,
                    b.get("reason"),
                    json.dumps(b, ensure_ascii=False),
                ),
            )
        con.commit()
    finally:
        con.close()


def upsert_result(
    fixture_id: int,
    final_score: Optional[str],
    result_1x2: Optional[str],
    status: Optional[str],
    raw: Optional[Dict[str, Any]] = None,
) -> None:
    """Store latest result snapshot for a fixture."""
    init_db()
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO results(fixture_id, final_score, result_1x2, status, updated_ts_utc, raw_json)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(fixture_id) DO UPDATE SET
              final_score=excluded.final_score,
              result_1x2=excluded.result_1x2,
              status=excluded.status,
              updated_ts_utc=excluded.updated_ts_utc,
              raw_json=excluded.raw_json
            """,
            (
                int(fixture_id),
                str(final_score) if final_score is not None else None,
                str(result_1x2) if result_1x2 is not None else None,
                str(status) if status is not None else None,
                _utc_iso(),
                json.dumps(raw or {}, ensure_ascii=False),
            ),
        )
        con.commit()
    finally:
        con.close()
