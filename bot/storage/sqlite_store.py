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
              raw_json TEXT,
              home_goals INTEGER,
              away_goals INTEGER,
              home_team_id INTEGER,
              away_team_id INTEGER,
              league_id INTEGER,
              season INTEGER
            );
            """
        )

        # Snapshot of fixtures/matches used as the pool for a run
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS fixtures (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              fixture_id INTEGER,
              league_name TEXT,
              country_name TEXT,
              kickoff_local TEXT,
              home_team TEXT,
              away_team TEXT,
              bucket INTEGER,
              odds_1 REAL,
              odds_x REAL,
              odds_2 REAL,
              raw_json TEXT,
              FOREIGN KEY(run_id) REFERENCES runs(id)
            );
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_run_id ON fixtures(run_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_fixture_id ON fixtures(fixture_id);")

        # One row per fixture_id (latest result snapshot)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_results_fixture_id ON results(fixture_id);")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS data_sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_name TEXT,
              fixture_id TEXT,
              data_type TEXT,
              value_json TEXT,
              confidence REAL,
              updated_at TEXT NOT NULL
            );
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_data_sources_fixture ON data_sources(fixture_id);")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS odds_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fixture_id TEXT,
              bookmaker TEXT,
              odds_1 REAL,
              odds_x REAL,
              odds_2 REAL,
              timestamp TEXT NOT NULL,
              source_json TEXT
            );
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_odds_history_fixture ON odds_history(fixture_id);")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS expert_picks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fixture_id TEXT,
              source TEXT,
              pick TEXT,
              confidence REAL,
              reasoning TEXT,
              author TEXT,
              timestamp TEXT
            );
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_expert_picks_fixture ON expert_picks(fixture_id);")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS prediction_market (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fixture_id TEXT,
              platform TEXT,
              outcome TEXT,
              probability REAL,
              market_odds REAL,
              timestamp TEXT
            );
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_prediction_market_fixture ON prediction_market(fixture_id);")

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


def insert_fixtures(run_id: int, matches: List[Dict[str, Any]]) -> None:
    if not matches:
        return

    init_db()
    con = _connect()
    try:
        for m in matches:
            odds = m.get("odds") or {}
            con.execute(
                """
                INSERT INTO fixtures(
                  run_id, fixture_id, league_name, country_name, kickoff_local, home_team, away_team,
                  bucket, odds_1, odds_x, odds_2, raw_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(run_id),
                    int(m.get("fixture_id")) if m.get("fixture_id") is not None else None,
                    m.get("league_name"),
                    m.get("country_name"),
                    m.get("kickoff_local"),
                    m.get("home_team"),
                    m.get("away_team"),
                    int(m.get("bucket")) if m.get("bucket") is not None else None,
                    float(odds.get("1")) if odds.get("1") is not None else None,
                    float(odds.get("X")) if odds.get("X") is not None else None,
                    float(odds.get("2")) if odds.get("2") is not None else None,
                    json.dumps(m, ensure_ascii=False),
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
    """Store latest result snapshot for a fixture.

    Best-effort: if schema has extra columns (home/away goals, team ids, league id), we fill them
    from raw provider payload. This enables Poisson/multi-market engines without extra APIs.
    """
    init_db()
    con = _connect()
    try:
        # detect extra columns
        cols = {r[1] for r in con.execute("PRAGMA table_info(results)").fetchall()}

        hg = ag = hid = aid = lid = season = None
        try:
            payload = raw or {}

            # API-Sports shape: {fixture, league, teams, goals}
            teams = payload.get("teams") or {}
            goals = payload.get("goals") or {}
            league = payload.get("league") or {}

            if isinstance(goals, dict):
                hg = goals.get("home")
                ag = goals.get("away")
            if isinstance(teams, dict):
                home = teams.get("home") or {}
                away = teams.get("away") or {}
                hid = home.get("id")
                aid = away.get("id")
            if isinstance(league, dict):
                lid = league.get("id")
                season = league.get("season")

            # SportMonks shape: {id, league:{id}, participants:[{id,meta:{location}}], scores:[...]}
            if (hid is None or aid is None) and isinstance(payload.get("participants"), list):
                home_p = away_p = None
                for p in (payload.get("participants") or []):
                    meta = p.get("meta") or {}
                    loc = (meta.get("location") or "").lower()
                    if loc == "home":
                        home_p = p
                    elif loc == "away":
                        away_p = p
                # fallback: first two
                parts = payload.get("participants") or []
                if home_p is None and len(parts) >= 1:
                    home_p = parts[0]
                if away_p is None and len(parts) >= 2:
                    away_p = parts[1]
                if home_p and hid is None:
                    hid = home_p.get("id")
                if away_p and aid is None:
                    aid = away_p.get("id")

            if lid is None and isinstance(payload.get("league"), dict):
                lid = (payload.get("league") or {}).get("id")
            if season is None:
                season = payload.get("season_id") or (payload.get("league") or {}).get("season_id")

            if (hg is None or ag is None) and isinstance(payload.get("scores"), list):
                # mimic daily_recap_main CURRENT extraction
                hg2 = ag2 = None
                for sc in (payload.get("scores") or []):
                    if (sc.get("description") or "").upper() != "CURRENT":
                        continue
                    score = sc.get("score") or {}
                    part = (score.get("participant") or "").lower()
                    goals_val = score.get("goals")
                    try:
                        goals_val = int(goals_val)
                    except Exception:
                        continue
                    if part == "home":
                        hg2 = goals_val
                    elif part == "away":
                        ag2 = goals_val
                if hg is None:
                    hg = hg2
                if ag is None:
                    ag = ag2

            # AllSportsAPI shape (best-effort): event_home_team_id / event_away_team_id / league_id / event_final_result
            if hid is None:
                hid = payload.get("event_home_team_id") or payload.get("home_team_id")
            if aid is None:
                aid = payload.get("event_away_team_id") or payload.get("away_team_id")
            if lid is None:
                lid = payload.get("league_key") or payload.get("league_id")
            if (hg is None or ag is None) and payload.get("event_final_result"):
                try:
                    a, b = [x.strip() for x in str(payload.get("event_final_result")).split("-", 1)]
                    hg = int(a)
                    ag = int(b)
                except Exception:
                    pass

            if hg is not None:
                hg = int(hg)
            if ag is not None:
                ag = int(ag)
            if hid is not None:
                hid = int(hid)
            if aid is not None:
                aid = int(aid)
            if lid is not None:
                lid = int(lid)
            if season is not None:
                season = int(season)
        except Exception:
            hg = ag = hid = aid = lid = season = None

        # build dynamic SQL depending on columns
        extra_fields = []
        extra_vals = []
        if "home_goals" in cols:
            extra_fields.append("home_goals")
            extra_vals.append(hg)
        if "away_goals" in cols:
            extra_fields.append("away_goals")
            extra_vals.append(ag)
        if "home_team_id" in cols:
            extra_fields.append("home_team_id")
            extra_vals.append(hid)
        if "away_team_id" in cols:
            extra_fields.append("away_team_id")
            extra_vals.append(aid)
        if "league_id" in cols:
            extra_fields.append("league_id")
            extra_vals.append(lid)
        if "season" in cols:
            extra_fields.append("season")
            extra_vals.append(season)

        if extra_fields:
            fields_sql = ", ".join(extra_fields)
            qmarks = ", ".join(["?"] * len(extra_fields))
            updates_sql = ",\n              ".join([f"{f}=excluded.{f}" for f in extra_fields])

            con.execute(
                f"""
                INSERT INTO results(fixture_id, final_score, result_1x2, status, updated_ts_utc, raw_json, {fields_sql})
                VALUES(?,?,?,?,?,?,{qmarks})
                ON CONFLICT(fixture_id) DO UPDATE SET
                  final_score=excluded.final_score,
                  result_1x2=excluded.result_1x2,
                  status=excluded.status,
                  updated_ts_utc=excluded.updated_ts_utc,
                  raw_json=excluded.raw_json,
                  {updates_sql}
                """,
                (
                    int(fixture_id),
                    str(final_score) if final_score is not None else None,
                    str(result_1x2) if result_1x2 is not None else None,
                    str(status) if status is not None else None,
                    _utc_iso(),
                    json.dumps(raw or {}, ensure_ascii=False),
                    *extra_vals,
                ),
            )
        else:
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


def insert_data_sources(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    init_db()
    con = _connect()
    try:
        for row in rows:
            con.execute(
                """
                INSERT INTO data_sources(source_name, fixture_id, data_type, value_json, confidence, updated_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    row.get("source_name"),
                    str(row.get("fixture_id")) if row.get("fixture_id") is not None else None,
                    row.get("data_type"),
                    json.dumps(row.get("value_json") or {}, ensure_ascii=False),
                    float(row.get("confidence")) if row.get("confidence") is not None else None,
                    _utc_iso(),
                ),
            )
        con.commit()
    finally:
        con.close()


def insert_odds_history(
    fixture_id: str,
    bookmaker: str,
    odds_1: Optional[float],
    odds_x: Optional[float],
    odds_2: Optional[float],
    source_rows: Optional[List[Dict[str, Any]]] = None,
) -> None:
    init_db()
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO odds_history(fixture_id, bookmaker, odds_1, odds_x, odds_2, timestamp, source_json)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                str(fixture_id),
                str(bookmaker or "unknown"),
                float(odds_1) if odds_1 is not None else None,
                float(odds_x) if odds_x is not None else None,
                float(odds_2) if odds_2 is not None else None,
                _utc_iso(),
                json.dumps(source_rows or [], ensure_ascii=False),
            ),
        )
        con.commit()
    finally:
        con.close()


def insert_expert_picks(fixture_id: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    init_db()
    con = _connect()
    try:
        for row in rows:
            con.execute(
                """
                INSERT INTO expert_picks(fixture_id, source, pick, confidence, reasoning, author, timestamp)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    str(fixture_id),
                    row.get("source"),
                    row.get("pick"),
                    float(row.get("confidence")) if row.get("confidence") is not None else None,
                    row.get("reasoning"),
                    row.get("author"),
                    row.get("timestamp"),
                ),
            )
        con.commit()
    finally:
        con.close()


def insert_prediction_markets(fixture_id: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    init_db()
    con = _connect()
    try:
        for row in rows:
            con.execute(
                """
                INSERT INTO prediction_market(fixture_id, platform, outcome, probability, market_odds, timestamp)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    str(fixture_id),
                    row.get("platform"),
                    row.get("outcome"),
                    float(row.get("probability")) if row.get("probability") is not None else None,
                    float(row.get("market_odds")) if row.get("market_odds") is not None else None,
                    row.get("timestamp"),
                ),
            )
        con.commit()
    finally:
        con.close()
