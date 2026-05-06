"""
scripts/build_database.py

FŐBB ADATBÁZIS FELTÖLTŐ SCRIPT

Ez az egyetlen script, amit kell futtatni az adatbázis feltöltéséhez.
Összefogja az összes forrást: football-data.org, Understat, stb.

FUTTATÁS:
  python scripts/build_database.py           # Teljes feltöltés (3 szezon)
  python scripts/build_database.py --quick   # Gyors mód (1 szezon)
  python scripts/build_database.py --check   # Csak ellenőrzés (nem tölt le)

BECSÜLT IDŐ:
  --quick : ~15 perc (1 szezon, top 5 liga)
  Normal  : ~60 perc (3 szezon, 9 liga)

BECSÜLT LEFEDETTSÉG UTÁNA:
  ~3000-6000 meccs az adatbázisban
  → Poisson modell valós adatokkal működhet
  → Tippminőség: LÉNYEGESEN JOBB
"""

from __future__ import annotations

import os
import sys
import sqlite3
import datetime
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# Projekt root hozzáadása sys.path-hoz
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def check_database_status() -> dict:
    """
    Ellenőrzi az adatbázis jelenlegi állapotát.
    Megmutatja hány meccs van tárolva ligánként.
    """
    db = _db_path()
    if not os.path.exists(db):
        print(f"⚠️  Adatbázis nem létezik: {db}")
        return {}

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        # Összes meccs
        total = con.execute("SELECT COUNT(*) as n FROM results WHERE home_goals IS NOT NULL").fetchone()
        print(f"\n📊 ADATBÁZIS ÁLLAPOT: {db}")
        print(f"   Összes meccs eredménnyel: {total['n']}")

        # Liga szintű bontás
        rows = con.execute("""
            SELECT league_id, season, COUNT(*) as n
            FROM results
            WHERE home_goals IS NOT NULL
            GROUP BY league_id, season
            ORDER BY n DESC
            LIMIT 30
        """).fetchall()

        if rows:
            print("\n   Liga/Szezon bontás (top 30):")
            for r in rows:
                print(f"   Liga ID {r['league_id']:>6} | {r['season']} | {r['n']:>4} meccs")

        # Csapatok száma
        teams_h = con.execute("SELECT COUNT(DISTINCT home_team_id) as n FROM results WHERE home_team_id IS NOT NULL").fetchone()
        teams_a = con.execute("SELECT COUNT(DISTINCT away_team_id) as n FROM results WHERE away_team_id IS NOT NULL").fetchone()
        print(f"\n   Különböző hazai csapatok: {teams_h['n']}")
        print(f"   Különböző vendég csapatok: {teams_a['n']}")

        # Legutóbbi meccs
        last = con.execute("""
            SELECT updated_ts_utc FROM results ORDER BY updated_ts_utc DESC LIMIT 1
        """).fetchone()
        if last:
            print(f"   Legutóbbi frissítés: {last['updated_ts_utc'][:19]}")

        return {"total": total['n']}
    finally:
        con.close()


def run_football_data_org(seasons_back: int = 3) -> int:
    """Football-data.org historikus adatok letöltése."""
    try:
        from bot.providers.football_data_org import build_historical_database, FREE_COMPETITIONS

        print(f"\n🌐 FOOTBALL-DATA.ORG letöltés ({seasons_back} szezon, {len(FREE_COMPETITIONS)} liga)...")
        print("   Becsült idő: ~40 perc (rate limit: 10 req/perc)")
        print("   API kulcs beállítva:", bool(os.getenv("FOOTBALL_DATA_API_KEY")))

        results = build_historical_database(seasons_back=seasons_back)
        total = sum(results.values())
        print(f"\n✅ Football-data.org: {total} meccs tárolva")
        return total
    except ImportError as e:
        print(f"❌ football_data_org import hiba: {e}")
        return 0
    except Exception as e:
        print(f"❌ Football-data.org hiba: {e}")
        log.exception("Football-data.org hiba")
        return 0


def run_understat(seasons_back: int = 2) -> int:
    """Understat.com xG + historikus adatok letöltése."""
    try:
        from bot.providers.understat_scraper import build_understat_database

        print(f"\n📈 UNDERSTAT.COM letöltés ({seasons_back} szezon, top 5 liga)...")
        print("   xG adatok + historikus eredmények")
        print("   API kulcs: NEM szükséges (nyilvános)")

        results = build_understat_database(seasons_back=seasons_back)
        total = sum(results.values())
        print(f"\n✅ Understat: {total} meccs tárolva")
        return total
    except ImportError as e:
        print(f"❌ understat_scraper import hiba: {e}")
        return 0
    except Exception as e:
        print(f"❌ Understat hiba: {e}")
        log.exception("Understat hiba")
        return 0


def run_existing_backfill() -> int:
    """A meglévő backfill script futtatása (ha van)."""
    try:
        backfill_path = os.path.join(os.path.dirname(__file__), "backfill_historical_data.py")
        if not os.path.exists(backfill_path):
            return 0

        print("\n📋 MEGLÉVŐ BACKFILL futtatása...")
        import subprocess
        result = subprocess.run(
            [sys.executable, backfill_path],
            capture_output=True, text=True, timeout=300,
        )
        print(result.stdout[-2000:] if result.stdout else "(nincs output)")
        if result.returncode != 0:
            print(f"⚠️  Backfill hiba (kód {result.returncode}): {result.stderr[-500:]}")
            return 0
        return 1
    except Exception as e:
        print(f"⚠️  Backfill hiba: {e}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Tippmix adatbázis feltöltő")
    parser.add_argument("--check", action="store_true", help="Csak ellenőrzés, nem tölt le")
    parser.add_argument("--quick", action="store_true", help="Gyors mód: 1 szezon, top 5 liga")
    parser.add_argument("--seasons", type=int, default=3, help="Hány szezon (alapért.: 3)")
    parser.add_argument("--source", choices=["all", "football-data", "understat"], default="all")
    args = parser.parse_args()

    print("=" * 60)
    print("  TIPPMIX ADATBÁZIS FELTÖLTŐ")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Ellenőrzés
    status = check_database_status()

    if args.check:
        print("\n✅ Ellenőrzés kész.")
        return

    seasons = 1 if args.quick else args.seasons

    # Adatbázis könyvtár létrehozása
    os.makedirs(os.path.dirname(_db_path()) or ".", exist_ok=True)

    grand_total = 0

    if args.source in ("all", "football-data"):
        total = run_football_data_org(seasons_back=seasons)
        grand_total += total

    if args.source in ("all", "understat"):
        total = run_understat(seasons_back=min(seasons, 2))
        grand_total += total

    if args.source == "all":
        run_existing_backfill()

    # Végső állapot
    print("\n" + "=" * 60)
    print(f"  FELTÖLTÉS KÉSZ — {grand_total} új meccs tárolva")
    print("=" * 60)
    check_database_status()

    # Figyelmeztetés ha kevés adat
    total_now = status.get("total", 0) + grand_total
    if total_now < 500:
        print("\n⚠️  FIGYELMEZTETÉS: Kevés meccs az adatbázisban!")
        print("   Tipp: Állítsd be a FOOTBALL_DATA_API_KEY secret-et")
        print("   (Ingyenes regisztráció: https://www.football-data.org/client/register)")
        print("   Ezzel 3x több adathoz juthatsz.")
    elif total_now < 2000:
        print("\n✅ Alapszintű adatbázis kész. A tippminőség javulni fog.")
        print("   Javasolt: futtasd hetente egyszer (GitHub Actions via workflow).")
    else:
        print(f"\n🎉 Kiemelkedő adatbázis: {total_now} meccs!")
        print("   A Poisson modell most már valós adatokkal tud dolgozni.")


if __name__ == "__main__":
    main()
