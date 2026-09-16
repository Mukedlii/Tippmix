"""
bot/storage/poisson_stats.py

A Poisson-modell statisztikai alapja: csapat- és liga-szintű gólátlagok
a saját, folyamatosan bővülő adatbázisból (data/tippmix.db).

Fejlesztések a korábbi (egyszerű, sima-átlag) verzióhoz képest:
  1. Hazai/vendég bontás — egy csapat hazai gólátlaga eltér a vendég
     gólátlagától, ezért külön számoljuk (Dixon-Coles gyakorlat).
  2. Időbeli súlyozás — a frissebb meccsek nagyobb súllyal esnek latba
     (exponenciális lecsengés), mert a forma számít.
  3. Bayes-i simítás (shrinkage) — kevés meccsnél (pl. 4-6 meccs) a nyers
     átlag zajos; a becslést a liga-átlag felé húzzuk, súlyozva a minta
     méretével, hogy ne legyen szélsőséges torzítás kevés adatból.

Minden adat kizárólag a saját adatbázisból (ingyenes scraping + napi
eredmény-visszacsatolás), nincs fizetős API.
"""

import os
import math
import sqlite3
import datetime
from typing import Any, Dict, Optional

from bot.storage.sqlite_store import _db_path  # type: ignore
from bot.storage.team_matcher import find_historical_team_id
from bot.storage.league_matcher import find_historical_league_id


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


def _recency_weight(match_date_iso: str, half_life_days: float) -> float:
    """Exponenciális lecsengés: a régebbi meccsek kisebb súllyal esnek latba.

    half_life_days idő alatt feleződik egy meccs súlya (pl. 45 nap).
    """
    try:
        match_dt = datetime.datetime.fromisoformat(str(match_date_iso).replace("Z", "+00:00"))
        if match_dt.tzinfo is None:
            match_dt = match_dt.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return 0.5  # ismeretlen dátum -> semleges súly

    now = datetime.datetime.now(datetime.timezone.utc)
    age_days = max(0.0, (now - match_dt).total_seconds() / 86400.0)
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)


def team_goal_rates(
    team_id: Optional[int] = None,
    team_name: Optional[str] = None,
    days: int = 120,
    venue: Optional[str] = None,  # "home" | "away" | None (kombinált)
    league_avg_for: Optional[float] = None,
    league_avg_against: Optional[float] = None,
) -> Optional[Dict[str, float]]:
    """
    Egy csapat gólátlaga (szerzett/kapott) az utóbbi N napban,
    időbeli súlyozással és opcionális hazai/vendég bontással.

    Args:
        team_id: csapat ID a jelenlegi providertől (opcionális)
        team_name: csapatnév fallback egyeztetéshez (opcionális)
        days: visszatekintési időszak napokban
        venue: "home" -> csak amikor a csapat hazai pályán játszott,
               "away" -> csak vendégként, None -> mindkettő (kombinált)
        league_avg_for/against: ha meg van adva, Bayes-i simításhoz
               (a nyers átlagot ez felé húzzuk kevés adatnál)

    Returns:
        Dict 'n' (súlyozott meccsszám), 'gf' (szerzett gól/meccs),
        'ga' (kapott gól/meccs), vagy None ha nincs adat.
    """
    if not os.path.exists(_db_path()):
        return None

    ensure_results_columns()
    start = _days_ago(days)
    half_life = float(os.getenv("TIPPMIX_RECENCY_HALFLIFE_DAYS", "45"))
    min_n = int(os.getenv("TIPPMIX_TEAM_MIN_N", "4"))

    def _query(tid: int) -> Optional[Dict[str, float]]:
        if venue == "home":
            sql = """
              SELECT home_goals AS gf, away_goals AS ga, updated_ts_utc AS dt
              FROM results
              WHERE home_team_id = ?
                AND updated_ts_utc >= ?
                AND status IN ('FT','AET','PEN')
                AND home_goals IS NOT NULL AND away_goals IS NOT NULL
            """
            params = (tid, start)
        elif venue == "away":
            sql = """
              SELECT away_goals AS gf, home_goals AS ga, updated_ts_utc AS dt
              FROM results
              WHERE away_team_id = ?
                AND updated_ts_utc >= ?
                AND status IN ('FT','AET','PEN')
                AND home_goals IS NOT NULL AND away_goals IS NOT NULL
            """
            params = (tid, start)
        else:
            sql = """
              SELECT
                CASE WHEN home_team_id = ? THEN home_goals ELSE away_goals END AS gf,
                CASE WHEN home_team_id = ? THEN away_goals ELSE home_goals END AS ga,
                updated_ts_utc AS dt
              FROM results
              WHERE (home_team_id = ? OR away_team_id = ?)
                AND updated_ts_utc >= ?
                AND status IN ('FT','AET','PEN')
                AND home_goals IS NOT NULL AND away_goals IS NOT NULL
            """
            params = (tid, tid, tid, tid, start)

        rows = con.execute(sql, params).fetchall()
        if not rows:
            return None

        w_sum = 0.0
        gf_w = 0.0
        ga_w = 0.0
        for r in rows:
            w = _recency_weight(r["dt"], half_life)
            w_sum += w
            gf_w += w * float(r["gf"] or 0)
            ga_w += w * float(r["ga"] or 0)

        n_raw = len(rows)
        if n_raw < min_n:
            return None

        gf_avg = gf_w / w_sum if w_sum > 0 else 0.0
        ga_avg = ga_w / w_sum if w_sum > 0 else 0.0
        return {"n": float(n_raw), "gf": gf_avg, "ga": ga_avg}

    con = _connect()
    try:
        result = None
        if team_id is not None:
            result = _query(int(team_id))

        if result is None and team_name:
            matched_id = find_historical_team_id(team_name)
            if matched_id and matched_id != team_id:
                result = _query(int(matched_id))

        if result is None:
            return None

        # Bayes-i simítás: kevés meccsnél húzzuk a ligáátlag felé.
        # Súly = n / (n + K), ahol K a "bizonytalansági" konstans (minél
        # nagyobb, annál óvatosabb a modell kevés adatnál).
        if league_avg_for is not None and league_avg_against is not None:
            k = float(os.getenv("TIPPMIX_SHRINKAGE_K", "6"))
            n = result["n"]
            blend = n / (n + k)
            result["gf"] = blend * result["gf"] + (1 - blend) * float(league_avg_for)
            result["ga"] = blend * result["ga"] + (1 - blend) * float(league_avg_against)

        return result
    finally:
        con.close()


def league_goal_baseline(
    league_id: Optional[int] = None,
    league_name: Optional[str] = None,
    days: int = 180,
) -> Optional[Dict[str, float]]:
    """
    Liga-szintű hazai/vendég gólátlag az utóbbi N napban, időbeli
    súlyozással.

    Args:
        league_id: liga ID a jelenlegi providertől (opcionális)
        league_name: liga név fallback egyeztetéshez (opcionális)
        days: visszatekintési időszak napokban

    Returns:
        Dict 'n' (meccsszám), 'home_for', 'away_for', vagy None.
    """
    if not os.path.exists(_db_path()):
        return None

    ensure_results_columns()
    start = _days_ago(days)
    half_life = float(os.getenv("TIPPMIX_RECENCY_HALFLIFE_DAYS", "45"))
    min_n = int(os.getenv("TIPPMIX_LEAGUE_MIN_N", "10"))

    def _query(lid: int) -> Optional[Dict[str, float]]:
        sql = """
          SELECT home_goals AS hg, away_goals AS ag, updated_ts_utc AS dt
          FROM results
          WHERE league_id = ?
            AND updated_ts_utc >= ?
            AND status IN ('FT','AET','PEN')
            AND home_goals IS NOT NULL AND away_goals IS NOT NULL
        """
        rows = con.execute(sql, (lid, start)).fetchall()
        if not rows:
            return None

        n_raw = len(rows)
        if n_raw < min_n:
            return None

        w_sum = 0.0
        hg_w = 0.0
        ag_w = 0.0
        for r in rows:
            w = _recency_weight(r["dt"], half_life)
            w_sum += w
            hg_w += w * float(r["hg"] or 0)
            ag_w += w * float(r["ag"] or 0)

        hg_avg = hg_w / w_sum if w_sum > 0 else 0.0
        ag_avg = ag_w / w_sum if w_sum > 0 else 0.0
        return {
            "n": float(n_raw),
            "home_for": max(0.6, min(2.5, hg_avg)),
            "away_for": max(0.5, min(2.3, ag_avg)),
        }

    con = _connect()
    try:
        if league_id is not None:
            result = _query(int(league_id))
            if result:
                return result

        if league_name:
            matched_id = find_historical_league_id(league_name)
            if matched_id and matched_id != league_id:
                result = _query(int(matched_id))
                if result:
                    return result

        return None
    finally:
        con.close()
