import argparse
import datetime
import os
import shutil
import sqlite3
from typing import List, Optional, Set

from bot.api_keys import resolve_sports_provider
from bot.results import _get_fixture_result  # re-use provider-aware fetch
from bot.storage.sqlite_store import init_db, upsert_result


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def _list_fixture_ids(days: int, max_ids: int) -> List[int]:
    """Collect fixture_ids from the last N days of runs (bets table)."""
    init_db()
    con = _connect()
    try:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        # run_date is stored like "YYYY-MM-DD" or display; to be safe, also use run_ts_utc
        rows = con.execute(
            """
            SELECT DISTINCT b.fixture_id
            FROM bets b
            JOIN runs r ON r.id = b.run_id
            WHERE b.fixture_id IS NOT NULL
              AND (substr(r.run_ts_utc, 1, 10) >= ? OR r.run_date >= ?)
            ORDER BY b.fixture_id DESC
            LIMIT ?
            """,
            (cutoff, cutoff, int(max_ids)),
        ).fetchall()
        out: List[int] = []
        for (fid,) in rows:
            try:
                out.append(int(fid))
            except Exception:
                pass
        return out
    finally:
        con.close()


def _archive_db(date_iso: str) -> Optional[str]:
    src = _db_path()
    if not os.path.isfile(src):
        return None
    out_dir = os.path.join("data", "archive", date_iso)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "tippmix.db")
    shutil.copy2(src, dst)
    return dst


def _prune_archives(keep_days: int = 8) -> None:
    base = os.path.join("data", "archive")
    if not os.path.isdir(base):
        return
    cutoff = datetime.date.today() - datetime.timedelta(days=keep_days)
    for name in os.listdir(base):
        p = os.path.join(base, name)
        if not os.path.isdir(p):
            continue
        try:
            dt = datetime.date.fromisoformat(name)
        except Exception:
            continue
        if dt < cutoff:
            shutil.rmtree(p, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=int(os.getenv("TIPPMIX_REFRESH_DAYS", "7")))
    ap.add_argument("--max", type=int, default=int(os.getenv("TIPPMIX_REFRESH_MAX", "400")))
    ap.add_argument("--archive", action="store_true", default=True)
    args = ap.parse_args()

    provider = resolve_sports_provider()
    print(f"Provider: {provider}")

    fids = _list_fixture_ids(days=max(1, args.days), max_ids=max(1, args.max))
    print(f"Fixture IDs to refresh: {len(fids)}")

    ok = 0
    fail = 0
    no_data = 0

    for i, fid in enumerate(fids, 1):
        try:
            fx = _get_fixture_result(int(fid))
            if not fx:
                no_data += 1
                upsert_result(int(fid), final_score=None, result_1x2=None, status="NO_DATA", raw={})
                continue
            # Store raw; daily_recap_main will interpret status/result, but we at least cache.
            upsert_result(int(fid), final_score=None, result_1x2=None, status="REFRESHED", raw=fx)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"Failed refresh fixture_id={fid}: {repr(e)}")

        if i % 25 == 0:
            print(f"Progress {i}/{len(fids)} ok={ok} fail={fail} no_data={no_data}")

    date_iso = datetime.date.today().isoformat()
    if args.archive:
        arch = _archive_db(date_iso)
        if arch:
            print(f"Archived DB to {arch}")
    _prune_archives(keep_days=8)

    print(f"Done. ok={ok} fail={fail} no_data={no_data}")


if __name__ == "__main__":
    main()
