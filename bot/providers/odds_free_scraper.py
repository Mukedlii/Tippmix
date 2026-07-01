from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from bot.providers.odds_scraper import (
    fetch_flashscore_odds,
    search_betexplorer,
    search_oddschecker,
    search_betfair_exchange,
)

CACHE_TTL_SECONDS = int(os.getenv("FREE_ODDS_CACHE_TTL_SECONDS", str(6 * 60 * 60)))
REQUEST_TIMEOUT = int(os.getenv("FREE_ODDS_REQUEST_TIMEOUT", "12"))

_ODDS_CACHE: Dict[str, Dict[str, Any]] = {}


def _cache_key(home_team: str, away_team: str) -> str:
    return f"{(home_team or '').strip().lower()}::{(away_team or '').strip().lower()}"


def _coerce_odds(value: Any) -> Optional[float]:
    try:
        v = float(value)
        if 1.01 <= v <= 35.0:
            return round(v, 2)
    except Exception:
        return None
    return None


def _pick_best_by_outcome(rows: List[Dict[str, Any]], key: str) -> tuple[Optional[float], Optional[str]]:
    best_val: Optional[float] = None
    best_src: Optional[str] = None
    for row in rows:
        v = _coerce_odds(row.get(key))
        if v is None:
            continue
        if best_val is None or v > best_val:
            best_val = v
            best_src = row.get("bookmaker") or row.get("source")
    return best_val, best_src


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _scrape_odds_com(home_team: str, away_team: str) -> Optional[Dict[str, Any]]:
    query = requests.utils.quote(f"{home_team} {away_team}")
    url = f"https://www.odds.com/search/?q={query}"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200 or not r.text:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        page_text_l = page_text.lower()
        home_l = (home_team or "").strip().lower()
        away_l = (away_team or "").strip().lower()
        if not home_l or not away_l:
            return None
        home_ok = home_l in page_text_l or all(part in page_text_l for part in home_l.split()[:2])
        away_ok = away_l in page_text_l or all(part in page_text_l for part in away_l.split()[:2])
        if not (home_ok and away_ok):
            return None

        import re

        nums = [float(x) for x in re.findall(r"\b\d{1,2}\.\d{1,2}\b", page_text)]
        if len(nums) < 3:
            return None
        return {
            "source": "odds.com",
            "bookmaker": "Odds.com",
            "odds_1": _coerce_odds(nums[0]),
            "odds_x": _coerce_odds(nums[1]),
            "odds_2": _coerce_odds(nums[2]),
        }
    except Exception:
        return None


def _fallback_predicted(predicted_odds: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(predicted_odds, dict):
        return None
    o1 = _coerce_odds(predicted_odds.get("1"))
    ox = _coerce_odds(predicted_odds.get("X"))
    o2 = _coerce_odds(predicted_odds.get("2"))
    if not (o1 and o2):
        return None
    return {
        "found": True,
        "sources": ["predicted"],
        "home_team": "",
        "away_team": "",
        "odds_1_avg": o1,
        "odds_x_avg": ox,
        "odds_2_avg": o2,
        "odds_1_best": o1,
        "odds_x_best": ox,
        "odds_2_best": o2,
        "best_bookmakers": {"1": "Predicted", "X": "Predicted", "2": "Predicted"},
        "used_fallback": True,
    }


def get_best_odds_free(
    home_team: str,
    away_team: str,
    predicted_odds: Optional[Dict[str, Any]] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    cache_key = _cache_key(home_team, away_team)
    now_ts = time.time()
    cached = _ODDS_CACHE.get(cache_key)
    if cached and not force_refresh and (now_ts - cached.get("ts", 0) <= CACHE_TTL_SECONDS):
        return dict(cached["data"])

    providers: List[Dict[str, Any]] = []

    flashscore = fetch_flashscore_odds(home_team, away_team)
    if flashscore:
        providers.append(
            {
                "source": "flashscore",
                "bookmaker": "FlashScore",
                "odds_1": flashscore.get("odds_1") or flashscore.get("odds_1_avg"),
                "odds_x": flashscore.get("odds_x") or flashscore.get("odds_x_avg"),
                "odds_2": flashscore.get("odds_2") or flashscore.get("odds_2_avg"),
            }
        )

    betexplorer = search_betexplorer(home_team, away_team)
    if betexplorer:
        providers.append(
            {
                "source": "betexplorer",
                "bookmaker": "BetExplorer",
                "odds_1": betexplorer.get("odds_1"),
                "odds_x": betexplorer.get("odds_x"),
                "odds_2": betexplorer.get("odds_2"),
            }
        )

    odds_com = _scrape_odds_com(home_team, away_team)
    if odds_com:
        providers.append(odds_com)

    oddschecker = search_oddschecker(home_team, away_team)
    if oddschecker:
        providers.append(
            {
                "source": "oddschecker",
                "bookmaker": "Oddschecker",
                "odds_1": oddschecker.get("odds_1"),
                "odds_x": oddschecker.get("odds_x"),
                "odds_2": oddschecker.get("odds_2"),
            }
        )

    betfair = search_betfair_exchange(home_team, away_team)
    if betfair:
        providers.append(
            {
                "source": "betfair",
                "bookmaker": "Betfair Exchange",
                "odds_1": betfair.get("odds_1"),
                "odds_x": betfair.get("odds_x"),
                "odds_2": betfair.get("odds_2"),
            }
        )

    if not providers:
        fallback = _fallback_predicted(predicted_odds)
        if fallback:
            _ODDS_CACHE[cache_key] = {"ts": now_ts, "data": fallback}
            return fallback
        return {"found": False, "sources": []}

    all_1 = [x for x in [_coerce_odds(p.get("odds_1")) for p in providers] if x]
    all_x = [x for x in [_coerce_odds(p.get("odds_x")) for p in providers] if x]
    all_2 = [x for x in [_coerce_odds(p.get("odds_2")) for p in providers] if x]
    if not all_1 or not all_2:
        fallback = _fallback_predicted(predicted_odds)
        if fallback:
            _ODDS_CACHE[cache_key] = {"ts": now_ts, "data": fallback}
            return fallback
        return {"found": False, "sources": [p["source"] for p in providers]}

    best_1, src_1 = _pick_best_by_outcome(providers, "odds_1")
    best_x, src_x = _pick_best_by_outcome(providers, "odds_x")
    best_2, src_2 = _pick_best_by_outcome(providers, "odds_2")

    out = {
        "found": True,
        "sources": [p["source"] for p in providers],
        "home_team": home_team,
        "away_team": away_team,
        "odds_1_avg": _avg(all_1),
        "odds_x_avg": _avg(all_x),
        "odds_2_avg": _avg(all_2),
        "odds_1_best": best_1,
        "odds_x_best": best_x,
        "odds_2_best": best_2,
        "best_bookmakers": {"1": src_1, "X": src_x, "2": src_2},
        "used_fallback": False,
    }

    _ODDS_CACHE[cache_key] = {"ts": now_ts, "data": out}
    return out
