"""
bot/self_learning.py

Önjavító visszacsatolás — a bot elemzi a saját múltbeli tippjeit
és az eredmények alapján javítja a következő tippeket.

Mit csinál:
  1. Lekéri a DB-ből az elmúlt 30/60 nap tippjeit + eredményeit
  2. Kiszámolja melyik liga / market / confidence szint teljesít jól
  3. Generál egy "tanulságok" szöveget ami bekerül az AI promptba
  4. Opcionálisan heti összefoglalót küld Telegramra

Használat:
  from bot.self_learning import build_learning_context, send_weekly_report_telegram
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)


def _db_path() -> str:
    return os.getenv("TIPPMIX_DB_PATH", os.path.join("data", "tippmix.db"))


def _connect() -> Optional[sqlite3.Connection]:
    path = _db_path()
    if not os.path.exists(path):
        log.warning(f"DB nem található: {path}")
        return None
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


# ──────────────────────────────────────────────
# 1. MÚLTBELI TIPPEK LEKÉRÉSE
# ──────────────────────────────────────────────

def fetch_resolved_bets(days: int = 60) -> list[dict]:
    """Lekéri azokat a tippeket ahol már van eredmény a DB-ben."""
    con = _connect()
    if not con:
        return []

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        rows = con.execute(
            """
            SELECT
                b.id,
                b.tier,
                b.league_name,
                b.home_team,
                b.away_team,
                b.tip,
                b.confidence,
                b.risk_level,
                b.kickoff_local,
                b.odds_pick,
                b.odds_1,
                b.odds_x,
                b.odds_2,
                r.result_1x2,
                r.final_score,
                r.home_goals,
                r.away_goals
            FROM bets b
            JOIN results r ON b.fixture_id = r.fixture_id
            JOIN runs ru ON b.run_id = ru.id
            WHERE ru.run_ts_utc >= ?
              AND r.result_1x2 IS NOT NULL
              AND r.result_1x2 != ''
            ORDER BY b.kickoff_local DESC
        """,
            (cutoff,),
        ).fetchall()

        return [dict(r) for r in rows]

    except Exception as e:
        log.warning(f"fetch_resolved_bets hiba: {e}")
        return []
    finally:
        con.close()


# ──────────────────────────────────────────────
# 2. TIPP ÉRTÉKELÉSE — nyert-e?
# ──────────────────────────────────────────────

def evaluate_bet(bet: dict) -> Optional[bool]:
    """Meghatározza hogy egy tipp nyert-e."""
    tip = (bet.get("tip") or "").strip().upper()
    result = (bet.get("result_1x2") or "").strip().upper()
    hg = bet.get("home_goals")
    ag = bet.get("away_goals")

    if not tip or not result:
        return None

    # 1X2
    if tip in ("1", "HAZAI GYŐZELEM", "HOME"):
        return result == "1"
    if tip in ("X", "DÖNTETLEN", "DRAW"):
        return result == "X"
    if tip in ("2", "VENDÉG GYŐZELEM", "AWAY"):
        return result == "2"

    # BTTS
    if "BTTS" in tip or "MINDKÉT" in tip:
        if hg is None or ag is None:
            return None
        both_scored = hg > 0 and ag > 0
        if "NO" in tip or "NEM" in tip:
            return not both_scored
        return both_scored

    # O/U
    if "OVER" in tip or "FELETT" in tip or "ALATT" in tip or "UNDER" in tip:
        if hg is None or ag is None:
            return None
        total = (hg or 0) + (ag or 0)
        if "2.5" in tip:
            if "OVER" in tip or "FELETT" in tip:
                return total > 2
            return total <= 2
        if "3.5" in tip:
            if "OVER" in tip or "FELETT" in tip:
                return total > 3
            return total <= 3

    return None


# ──────────────────────────────────────────────
# 3. STATISZTIKÁK
# ──────────────────────────────────────────────

def compute_stats(bets: list[dict]) -> dict:
    stats = {
        "total": 0,
        "won": 0,
        "lost": 0,
        "hitrate": 0.0,
        "by_league": defaultdict(lambda: {"total": 0, "won": 0}),
        "by_market": defaultdict(lambda: {"total": 0, "won": 0}),
        "by_confidence": {
            "high": {"total": 0, "won": 0},
            "medium": {"total": 0, "won": 0},
            "low": {"total": 0, "won": 0},
        },
        "by_tier": defaultdict(lambda: {"total": 0, "won": 0}),
        "worst_leagues": [],
        "best_leagues": [],
        "best_markets": [],
    }

    for bet in bets:
        result = evaluate_bet(bet)
        if result is None:
            continue

        stats["total"] += 1
        if result:
            stats["won"] += 1
        else:
            stats["lost"] += 1

        league = (bet.get("league_name") or "Ismeretlen").strip()
        stats["by_league"][league]["total"] += 1
        if result:
            stats["by_league"][league]["won"] += 1

        tip = (bet.get("tip") or "").upper()
        if "BTTS" in tip or "MINDKÉT" in tip:
            market = "BTTS"
        elif "OVER" in tip or "UNDER" in tip or "FELETT" in tip or "ALATT" in tip:
            market = "OU"
        elif tip in ("1", "X", "2") or "HAZAI" in tip or "VENDÉG" in tip or "DÖNTETLEN" in tip:
            market = "1X2"
        else:
            market = "Egyéb"

        stats["by_market"][market]["total"] += 1
        if result:
            stats["by_market"][market]["won"] += 1

        try:
            conf = float(bet.get("confidence") or 0)
            if conf > 1.0:
                conf = conf / 5.0
            if conf >= 0.65:
                bucket = "high"
            elif conf >= 0.50:
                bucket = "medium"
            else:
                bucket = "low"
        except Exception:
            bucket = "medium"

        stats["by_confidence"][bucket]["total"] += 1
        if result:
            stats["by_confidence"][bucket]["won"] += 1

        tier = bet.get("tier", "FREE")
        stats["by_tier"][tier]["total"] += 1
        if result:
            stats["by_tier"][tier]["won"] += 1

    if stats["total"] > 0:
        stats["hitrate"] = round(stats["won"] / stats["total"] * 100, 1)

    league_stats = []
    for league, data in stats["by_league"].items():
        if data["total"] >= 3:
            hr = data["won"] / data["total"] * 100
            league_stats.append({"league": league, "hitrate": round(hr, 1), "total": data["total"]})

    league_stats.sort(key=lambda x: x["hitrate"], reverse=True)
    stats["best_leagues"] = league_stats[:5]
    stats["worst_leagues"] = league_stats[-3:] if len(league_stats) >= 3 else []

    market_stats = []
    for market, data in stats["by_market"].items():
        if data["total"] >= 3:
            hr = data["won"] / data["total"] * 100
            market_stats.append({"market": market, "hitrate": round(hr, 1), "total": data["total"]})
    market_stats.sort(key=lambda x: x["hitrate"], reverse=True)
    stats["best_markets"] = market_stats

    return stats


# ──────────────────────────────────────────────
# 4. TANULSÁGOK PROMPT
# ──────────────────────────────────────────────

def build_learning_context(days: int = 30) -> str:
    bets = fetch_resolved_bets(days=days)
    if not bets:
        return ""

    stats = compute_stats(bets)
    if stats["total"] < 5:
        return ""

    lines = [
        f"=== SAJÁT TELJESÍTMÉNY TANULSÁGOK (utolsó {days} nap) ===",
        f"Összesített hitrate: {stats['hitrate']}% ({stats['total']} tippből {stats['won']} nyert)",
        "",
    ]

    best = stats.get("best_leagues", [])
    if best:
        lines.append("✅ Legjobb ligák (itt adj több tippet):")
        for lg in best[:3]:
            lines.append(f"  - {lg['league']}: {lg['hitrate']}% ({lg['total']} tipp)")
        lines.append("")

    worst = stats.get("worst_leagues", [])
    if worst:
        low_performers = [lg for lg in worst if lg["hitrate"] < 45]
        if low_performers:
            lines.append("❌ Kerülendő ligák (gyenge eredmény):")
            for lg in low_performers:
                lines.append(f"  - {lg['league']}: {lg['hitrate']}% ({lg['total']} tipp) ← KERÜLD vagy csökkentsd")
            lines.append("")

    markets = stats.get("best_markets", [])
    if markets:
        lines.append("📊 Market teljesítmény:")
        for m in markets:
            trend = "→ folytatni" if m["hitrate"] >= 55 else ("→ óvatos" if m["hitrate"] >= 45 else "→ KERÜLD")
            lines.append(f"  - {m['market']}: {m['hitrate']}% ({m['total']} tipp) {trend}")
        lines.append("")

    conf = stats.get("by_confidence", {})
    lines.append("🎯 Confidence szintek teljesítménye:")
    for label, bucket in (("high", "Magas confidence (>65%)"), ("medium", "Közepes confidence (50-65%)"), ("low", "Alacsony confidence (<50%)")):
        b = conf.get(label, {})
        if b.get("total", 0) >= 3:
            hr = round(b["won"] / b["total"] * 100, 1)
            lines.append(f"  - {bucket}: {hr}% hitrate")

    lines.append("")
    lines.append("INSTRUKCIÓ: A fenti tanulságok alapján:")
    lines.append("- Részesítsd előnyben a jól teljesítő ligákat és marketeket")
    lines.append("- Kerüld vagy csökkentsd a gyengén teljesítőket")
    lines.append("- Ha a confidence szintek nem korrelálnak a hitrate-tel, kalibrálj")
    lines.append("=== TANULSÁGOK VÉGE ===")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 5. HETI RIPORT TELEGRAM
# ──────────────────────────────────────────────

def format_weekly_report() -> str:
    bets_7 = fetch_resolved_bets(days=7)
    bets_30 = fetch_resolved_bets(days=30)

    stats_7 = compute_stats(bets_7)
    stats_30 = compute_stats(bets_30)

    lines = ["📊 *HETI TELJESÍTMÉNY ÖSSZEFOGLALÓ*", ""]

    if stats_7["total"] == 0:
        lines.append("_Nincs elég adat az elmúlt 7 napból._")
        return "\n".join(lines)

    lines.append("*Elmúlt 7 nap:*")
    lines.append(f"  ✅ Nyert: {stats_7['won']} | ❌ Veszett: {stats_7['lost']} | 📈 Hitrate: {stats_7['hitrate']}%")
    lines.append("")

    if stats_30["total"] >= 5:
        lines.append("*Elmúlt 30 nap:*")
        lines.append(f"  ✅ Nyert: {stats_30['won']} | ❌ Veszett: {stats_30['lost']} | 📈 Hitrate: {stats_30['hitrate']}%")
        lines.append("")

    best = stats_30.get("best_leagues", [])
    if best:
        lines.append("🏆 *Legjobb ligák (30 nap):*")
        for lg in best[:3]:
            lines.append(f"  - {lg['league']}: {lg['hitrate']}% ({lg['total']} tipp)")
        lines.append("")

    markets = stats_30.get("best_markets", [])
    if markets:
        lines.append("🎯 *Market teljesítmény:*")
        for m in markets:
            emoji = "✅" if m["hitrate"] >= 55 else ("⚠️" if m["hitrate"] >= 45 else "❌")
            lines.append(f"  {emoji} {m['market']}: {m['hitrate']}% ({m['total']} tipp)")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("_A bot folyamatosan tanul és javítja a tippeket az eredmények alapján._")

    return "\n".join(lines)


def send_weekly_report_telegram() -> None:
    import requests as req

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = [
        os.getenv("TELEGRAM_CHAT_ID_VIP", ""),
        os.getenv("TELEGRAM_CHAT_ID_PUBLIC", ""),
        os.getenv("TELEGRAM_CHAT_ID_EN", ""),
    ]

    report = format_weekly_report()
    if not report:
        log.info("Nincs elég adat a heti riporthoz.")
        return

    for chat_id in chat_ids:
        if not chat_id or not token:
            continue
        try:
            r = req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": report, "parse_mode": "Markdown"},
                timeout=10,
            )
            if r.status_code == 200:
                log.info(f"Heti riport elküldve: {chat_id}")
            else:
                log.warning(f"Telegram hiba {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"Telegram küldés hiba: {e}")
