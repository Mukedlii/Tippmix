"""
bot/providers/odds_scraper.py

Ingyenes odds scraper — API nélkül, nyilvános weboldalakról.

Források (mind ingyenes, nyilvános):
  1. OddsPortal.com — aggregált odds több bukmékertől
  2. Flashscore.com — élő és előzetes odds
  3. SofaScore.com — odds adatok
  4. Betexplorer.com — historikus + aktuális odds

Mit ad vissza:
  - 1X2 odds több bukmékertől
  - Legjobb elérhető odds (max odds a piacon)
  - Átlag odds (piaci konszenzus)
  - Odds mozgás (nyitó vs. jelenlegi) — ez jelzi a "smart money" irányt
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}


def _get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        time.sleep(random.uniform(1.0, 2.2))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.debug(f"HTTP {r.status_code} → {url}")
    except Exception as e:
        log.debug(f"Fetch failed {url}: {e}")
    return None


# ──────────────────────────────────────────────
# 1. ODDSPORTAL — legjobb aggregátor
# ──────────────────────────────────────────────

def search_oddsportal(home_team: str, away_team: str) -> Optional[dict]:
    """OddsPortal keresés a meccsre."""
    query = f"{home_team} {away_team}"
    search_url = f"https://www.oddsportal.com/search/results/{requests.utils.quote(query)}/"
    html = _get(search_url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")

        # OddsPortal dinamikus, de néha van HTML fallback
        rows = soup.select("div.eventRow, tr.deactivate")
        for row in rows:
            text = row.get_text(strip=True).lower()
            if home_team.lower()[:5] in text or away_team.lower()[:5] in text:
                odds_spans = row.select("span.odds-nowrp, td.odds-nowrp")
                if len(odds_spans) >= 3:
                    try:
                        return {
                            "source": "oddsportal",
                            "odds_1": float(odds_spans[0].get_text(strip=True)),
                            "odds_x": float(odds_spans[1].get_text(strip=True)),
                            "odds_2": float(odds_spans[2].get_text(strip=True)),
                        }
                    except ValueError:
                        continue

        # Best-effort JSON sniff (not guaranteed)
        scripts = soup.find_all("script")
        for script in scripts:
            content = script.string or ""
            if not content:
                continue
            if "odds" in content.lower() and home_team.lower()[:4] in content.lower():
                matches = re.findall(r'"odds":\s*\{[^}]+\}', content)
                if matches:
                    log.debug(f"OddsPortal JSON snippet: {matches[0][:120]}")
                    break

    except Exception as e:
        log.debug(f"OddsPortal parse error: {e}")

    return None


# ──────────────────────────────────────────────
# 2. BETEXPLORER — megbízható
# ──────────────────────────────────────────────

def search_betexplorer(home_team: str, away_team: str) -> Optional[dict]:
    """BetExplorer.com keresés."""
    query = f"{home_team} {away_team}"
    search_url = f"https://www.betexplorer.com/search/?q={requests.utils.quote(query)}"
    html = _get(search_url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table#sortable-1 tr, .table-main tr")

        for row in rows:
            text = row.get_text(strip=True).lower()
            if home_team.lower()[:4] in text and away_team.lower()[:4] in text:
                cells = row.select("td")
                if len(cells) >= 5:
                    try:
                        odds_1 = float(cells[-3].get_text(strip=True))
                        odds_x = float(cells[-2].get_text(strip=True))
                        odds_2 = float(cells[-1].get_text(strip=True))
                        return {
                            "source": "betexplorer",
                            "odds_1": odds_1,
                            "odds_x": odds_x,
                            "odds_2": odds_2,
                        }
                    except (ValueError, IndexError):
                        continue

    except Exception as e:
        log.debug(f"BetExplorer parse error: {e}")

    return None


# ──────────────────────────────────────────────
# 3. THE ODDS API — ingyenes tier (500 req/hó)
# ──────────────────────────────────────────────

def fetch_theoddsapi(
    home_team: str,
    away_team: str,
    api_key: Optional[str] = None,
) -> Optional[dict]:
    import os

    key = (api_key or os.getenv("ODDS_API_KEY", "")).strip()
    if not key:
        return None

    url = "https://api.the-odds-api.com/v4/sports/soccer/odds/"
    params = {
        "apiKey": key,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": "bet365,unibet,pinnacle,betfair",
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            log.debug(f"TheOddsAPI HTTP {r.status_code}")
            return None

        games = r.json()
        home_l = home_team.lower()
        away_l = away_team.lower()

        for game in games:
            h = (game.get("home_team") or "").lower()
            a = (game.get("away_team") or "").lower()

            # best-effort fuzzy match
            if not (home_l[:5] in h and away_l[:5] in a) and not (away_l[:5] in a and home_l[:5] in h):
                continue

            all_odds = {"1": [], "X": [], "2": []}
            bookmakers_found = []

            for bk in (game.get("bookmakers") or []):
                bk_name = bk.get("key", "")
                for market in (bk.get("markets") or []):
                    if market.get("key") != "h2h":
                        continue
                    outcomes = {o.get("name"): o.get("price") for o in (market.get("outcomes") or [])}
                    h_odds = outcomes.get(game.get("home_team"))
                    a_odds = outcomes.get(game.get("away_team"))
                    d_odds = outcomes.get("Draw")
                    if h_odds:
                        all_odds["1"].append(h_odds)
                    if d_odds:
                        all_odds["X"].append(d_odds)
                    if a_odds:
                        all_odds["2"].append(a_odds)
                    bookmakers_found.append(bk_name)

            if all_odds["1"]:
                return {
                    "source": "theoddsapi",
                    "home_team": game.get("home_team"),
                    "away_team": game.get("away_team"),
                    "odds_1_avg": round(sum(all_odds["1"]) / len(all_odds["1"]), 2),
                    "odds_x_avg": round(sum(all_odds["X"]) / len(all_odds["X"]), 2) if all_odds["X"] else None,
                    "odds_2_avg": round(sum(all_odds["2"]) / len(all_odds["2"]), 2),
                    "odds_1_best": max(all_odds["1"]),
                    "odds_x_best": max(all_odds["X"]) if all_odds["X"] else None,
                    "odds_2_best": max(all_odds["2"]),
                    "bookmakers": bookmakers_found,
                    "bookmaker_count": len(set(bookmakers_found)),
                }

    except Exception as e:
        log.debug(f"TheOddsAPI error: {e}")

    return None


# ──────────────────────────────────────────────
# 4. FLASH SCORE (best effort)
# ──────────────────────────────────────────────

def fetch_flashscore_odds(home_team: str, away_team: str) -> Optional[dict]:
    search_url = f"https://www.flashscore.com/search/?q={requests.utils.quote(home_team + ' ' + away_team)}"
    html = _get(search_url)
    if not html:
        return None

    try:
        match = re.search(
            r'"odds":\s*\{.*?"home":\s*([\d.]+).*?"draw":\s*([\d.]+).*?"away":\s*([\d.]+)',
            html,
            re.DOTALL,
        )
        if match:
            return {
                "source": "flashscore",
                "odds_1": float(match.group(1)),
                "odds_x": float(match.group(2)),
                "odds_2": float(match.group(3)),
            }
    except Exception as e:
        log.debug(f"Flashscore parse error: {e}")

    return None


# ──────────────────────────────────────────────
# 5. FŐ FÜGGVÉNY — összesített odds gyűjtés
# ──────────────────────────────────────────────

def get_best_odds(home_team: str, away_team: str) -> dict:
    results: dict = {}
    sources_tried: list[str] = []

    theodds = fetch_theoddsapi(home_team, away_team)
    if theodds:
        results["theoddsapi"] = theodds
        sources_tried.append("theoddsapi")
        log.info(
            f"[Odds] TheOddsAPI: 1={theodds.get('odds_1_avg')} X={theodds.get('odds_x_avg')} 2={theodds.get('odds_2_avg')}"
        )

    oddsportal = search_oddsportal(home_team, away_team)
    if oddsportal:
        results["oddsportal"] = oddsportal
        sources_tried.append("oddsportal")
        log.info(
            f"[Odds] OddsPortal: 1={oddsportal.get('odds_1')} X={oddsportal.get('odds_x')} 2={oddsportal.get('odds_2')}"
        )

    betexp = search_betexplorer(home_team, away_team)
    if betexp:
        results["betexplorer"] = betexp
        sources_tried.append("betexplorer")

    all_1: list[float] = []
    all_x: list[float] = []
    all_2: list[float] = []

    for _src, data in results.items():
        o1 = data.get("odds_1") or data.get("odds_1_avg")
        ox = data.get("odds_x") or data.get("odds_x_avg")
        o2 = data.get("odds_2") or data.get("odds_2_avg")
        if o1 and 1.01 <= float(o1) <= 25:
            all_1.append(float(o1))
        if ox and 1.01 <= float(ox) <= 25:
            all_x.append(float(ox))
        if o2 and 1.01 <= float(o2) <= 25:
            all_2.append(float(o2))

    if not all_1:
        return {"sources": sources_tried, "found": False}

    avg_1 = round(sum(all_1) / len(all_1), 2)
    avg_x = round(sum(all_x) / len(all_x), 2) if all_x else None
    avg_2 = round(sum(all_2) / len(all_2), 2)

    best_1 = max(all_1)
    best_x = max(all_x) if all_x else None
    best_2 = max(all_2)

    imp_1 = round(1 / avg_1, 3) if avg_1 else None
    imp_x = round(1 / avg_x, 3) if avg_x else None
    imp_2 = round(1 / avg_2, 3) if avg_2 else None

    import statistics

    spread_1 = round(statistics.stdev(all_1), 3) if len(all_1) > 1 else 0
    spread_2 = round(statistics.stdev(all_2), 3) if len(all_2) > 1 else 0

    return {
        "found": True,
        "sources": sources_tried,
        "home_team": home_team,
        "away_team": away_team,
        "odds_1_avg": avg_1,
        "odds_x_avg": avg_x,
        "odds_2_avg": avg_2,
        "odds_1_best": best_1,
        "odds_x_best": best_x,
        "odds_2_best": best_2,
        "implied_prob_1": imp_1,
        "implied_prob_x": imp_x,
        "implied_prob_2": imp_2,
        "odds_spread_1": spread_1,
        "odds_spread_2": spread_2,
        "market_uncertainty": "magas" if max(spread_1, spread_2) > 0.15 else "alacsony",
        "raw": results,
    }


def format_odds_for_prompt(odds_data: dict) -> str:
    if not odds_data or not odds_data.get("found"):
        return ""

    lines = ["📊 ODDS ADATOK (piaci árazás):"]

    o1 = odds_data.get("odds_1_avg")
    ox = odds_data.get("odds_x_avg")
    o2 = odds_data.get("odds_2_avg")

    if o1:
        lines.append(f"  Átlag odds: 1={o1} | X={ox or '?'} | 2={o2}")

    b1 = odds_data.get("odds_1_best")
    b2 = odds_data.get("odds_2_best")
    if b1 and b1 != o1:
        lines.append(f"  Legjobb odds: 1={b1} | 2={b2}")

    i1 = odds_data.get("implied_prob_1")
    ix = odds_data.get("implied_prob_x")
    i2 = odds_data.get("implied_prob_2")
    if i1:
        if ix:
            lines.append(f"  Piaci valószínűség: hazai={i1:.1%} | döntetlen={ix:.1%} | vendég={i2:.1%}")
        else:
            lines.append(f"  Piaci valószínűség: hazai={i1:.1%} | vendég={i2:.1%}")

    uncertainty = odds_data.get("market_uncertainty")
    if uncertainty == "magas":
        lines.append("  ⚠️ Piaci bizonytalanság: MAGAS — potenciális value lehetőség!")

    sources = odds_data.get("sources", [])
    if sources:
        lines.append(f"  Források: {', '.join(sources)}")

    lines.append("")
    lines.append("  FONTOS: Ha a Poisson/AI által becsült valószínűség MAGASABB")
    lines.append("  mint a piaci implied probability, ott van VALUE (pozitív EV).")

    return "\n".join(lines)
