"""
bot/providers/free_fixtures.py

Ingyenes meccs lekérő — API nélkül, nyilvános weboldalakról scraping.

Források:
  1. Flashscore.com    — legteljesebb, napi meccslista
  2. SofaScore.com     — JSON API (publikus, nincs auth)
  3. LiveScore.com     — egyszerű HTML scraping
  4. Football-data.org — TÉNYLEGESEN ingyenes API (regisztrálj, kártyakell nincs)
                         10 req/perc, top 12 liga, ajánlott elsődleges forrásnak

Beállítás a matches.py-ban:
  SPORTS_DATA_PROVIDER=free_scraper  (GitHub Actions Variable)

Semmi secret nem kell hozzá az alap működéshez.
"""

from __future__ import annotations

import datetime
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
}


def _get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        time.sleep(random.uniform(1.2, 2.0))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.debug(f"HTTP {r.status_code} → {url}")
    except Exception as e:
        log.debug(f"Fetch failed {url}: {e}")
    return None


def _json_get(url: str, extra_headers: dict | None = None, timeout: int = 15) -> Optional[dict]:
    try:
        time.sleep(random.uniform(1.0, 1.8))
        h = {**HEADERS, "Accept": "application/json"}
        if extra_headers:
            h.update(extra_headers)
        r = requests.get(url, headers=h, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        log.debug(f"JSON HTTP {r.status_code} → {url}")
    except Exception as e:
        log.debug(f"JSON fetch failed {url}: {e}")
    return None


# ──────────────────────────────────────────────
# 1. SOFASCORE — publikus JSON API
# ──────────────────────────────────────────────

SOFASCORE_TOP_LEAGUES = {
    "Premier League": 17,
    "La Liga": 8,
    "Bundesliga": 35,
    "Serie A": 23,
    "Ligue 1": 34,
    "Champions League": 7,
    "Europa League": 679,
    "Eredivisie": 37,
    "Primeira Liga": 238,
    "Scottish Premiership": 36,
    "Championship": 18,
    "Conference League": 17015,
}


def fetch_sofascore_day(date_str: str) -> list[dict]:
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"

    extra_headers = {
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
    }

    data = _json_get(url, extra_headers=extra_headers)
    if not data:
        log.warning("[SofaScore] Nem sikerült lekérni a napi meccseket")
        return []

    events = data.get("events", [])
    log.info(f"[SofaScore] {len(events)} esemény lekérve {date_str}-re")

    matches: list[dict] = []
    for ev in events:
        try:
            sport = ev.get("sport") or {}
            if sport.get("id") != 1 and sport.get("slug") != "football":
                continue

            tournament = ev.get("tournament") or {}
            category = tournament.get("category") or {}

            league_name = tournament.get("name", "")
            country_name = category.get("name", "")

            home_obj = ev.get("homeTeam") or {}
            away_obj = ev.get("awayTeam") or {}
            home_team = home_obj.get("shortName") or home_obj.get("name", "")
            away_team = away_obj.get("shortName") or away_obj.get("name", "")

            if not home_team or not away_team:
                continue

            status = ev.get("status") or {}
            status_type = status.get("type", "")
            if status_type not in ("notstarted", "scheduled", ""):
                continue

            start_ts = ev.get("startTimestamp")
            if start_ts:
                kickoff = datetime.datetime.utcfromtimestamp(start_ts).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            else:
                kickoff = f"{date_str}T12:00:00+00:00"

            fixture_id = ev.get("id")
            home_id = home_obj.get("id")
            away_id = away_obj.get("id")
            league_id = tournament.get("uniqueTournament", {}).get("id") or tournament.get("id")

            matches.append(
                {
                    "sport": "football",
                    "fixture_id": int(fixture_id) if fixture_id else None,
                    "league_id": int(league_id) if league_id else None,
                    "league_name": league_name,
                    "country_name": country_name,
                    "kickoff_local": kickoff,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_team_id": int(home_id) if home_id else None,
                    "away_team_id": int(away_id) if away_id else None,
                    "odds": {},
                    "standings": {},
                    "injuries": [],
                    "source": "sofascore",
                }
            )
        except Exception as e:
            log.debug(f"[SofaScore] Event parse error: {e}")
            continue

    log.info(f"[SofaScore] {len(matches)} labdarúgó meccs feldolgozva")
    return matches


def fetch_sofascore_odds(fixture_id: int) -> Optional[dict]:
    url = f"https://api.sofascore.com/api/v1/event/{fixture_id}/odds/1/all"
    extra_headers = {
        "Referer": f"https://www.sofascore.com/event/{fixture_id}",
        "Origin": "https://www.sofascore.com",
    }

    data = _json_get(url, extra_headers=extra_headers)
    if not data:
        return None

    try:
        markets = data.get("markets") or []
        for market in markets:
            if "1x2" in (market.get("marketName") or "").lower() or market.get("marketId") == 1:
                choices = market.get("choices") or []
                odds_map: dict[str, float] = {}
                for choice in choices:
                    name = choice.get("name", "")
                    dec = choice.get("decimalValue")
                    if dec is None:
                        continue
                    try:
                        val = float(dec)
                    except Exception:
                        continue
                    if name == "1" or "home" in name.lower():
                        odds_map["1"] = val
                    elif name.upper() == "X" or "draw" in name.lower():
                        odds_map["X"] = val
                    elif name == "2" or "away" in name.lower():
                        odds_map["2"] = val

                if odds_map.get("1") and odds_map.get("2"):
                    return odds_map
    except Exception as e:
        log.debug(f"[SofaScore] Odds parse error for {fixture_id}: {e}")

    return None


# ──────────────────────────────────────────────
# 2. FLASHSCORE — HTML scraping
# ──────────────────────────────────────────────

def fetch_flashscore_day(date_str: str) -> list[dict]:
    date_nodash = date_str.replace("-", "")
    url = f"https://www.flashscore.com/football/#{date_nodash}/"

    html = _get(url)
    if not html:
        log.warning("[Flashscore] Nem sikerült lekérni")
        return []

    try:
        soup = BeautifulSoup(html, "html.parser")

        matches: list[dict] = []
        current_league = "Unknown"
        current_country = ""

        for row in soup.select(".event__match, .event__header"):
            if "event__header" in (row.get("class") or []):
                header_text = row.get_text(strip=True)
                if ":" in header_text:
                    parts = header_text.split(":", 1)
                    current_country = parts[0].strip()
                    current_league = parts[1].strip()
                else:
                    current_league = header_text
                continue

            home_el = row.select_one(".event__participant--home")
            away_el = row.select_one(".event__participant--away")
            time_el = row.select_one(".event__time")

            if not home_el or not away_el:
                continue

            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)
            kick_time = time_el.get_text(strip=True) if time_el else ""

            if not home or not away:
                continue

            fid = hash(f"{home}_{away}_{date_str}") & 0x7FFFFFFF
            kickoff = f"{date_str}T{kick_time}:00+00:00" if kick_time else f"{date_str}T12:00:00+00:00"

            matches.append(
                {
                    "sport": "football",
                    "fixture_id": fid,
                    "league_name": current_league,
                    "country_name": current_country,
                    "kickoff_local": kickoff,
                    "home_team": home,
                    "away_team": away,
                    "odds": {},
                    "standings": {},
                    "injuries": [],
                    "source": "flashscore",
                }
            )

        log.info(f"[Flashscore] {len(matches)} meccs scrape-lve")
        return matches

    except Exception as e:
        log.warning(f"[Flashscore] Parse error: {e}")
        return []


# ──────────────────────────────────────────────
# 3. LIVESCORE — publikus API
# ──────────────────────────────────────────────

def fetch_livescore_day(date_str: str) -> list[dict]:
    url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{date_str.replace('-', '')}/0"
    data = _json_get(url)
    if not data:
        return []

    try:
        stages = data.get("Stages") or []
        matches: list[dict] = []

        for stage in stages:
            league_name = (stage.get("Cnm", "") + " " + stage.get("Snm", "")).strip()
            country_name = stage.get("Cnm", "")
            events = stage.get("Events") or []

            for ev in events:
                home = ev.get("T1", [{}])[0].get("Nm", "") if ev.get("T1") else ""
                away = ev.get("T2", [{}])[0].get("Nm", "") if ev.get("T2") else ""

                if not home or not away:
                    continue

                kickoff = f"{date_str}T12:00:00+00:00"
                esd = ev.get("Esd", "")
                if esd and len(str(esd)) >= 12:
                    esd_str = str(esd)
                    kickoff = f"{esd_str[:4]}-{esd_str[4:6]}-{esd_str[6:8]}T{esd_str[8:10]}:{esd_str[10:12]}:00+00:00"

                fid = ev.get("Eid") or (hash(f"{home}_{away}_{date_str}") & 0x7FFFFFFF)

                matches.append(
                    {
                        "sport": "football",
                        "fixture_id": int(fid),
                        "league_name": league_name,
                        "country_name": country_name,
                        "kickoff_local": kickoff,
                        "home_team": home,
                        "away_team": away,
                        "odds": {},
                        "standings": {},
                        "injuries": [],
                        "source": "livescore",
                    }
                )

        log.info(f"[LiveScore] {len(matches)} meccs lekérve")
        return matches

    except Exception as e:
        log.warning(f"[LiveScore] Parse error: {e}")
        return []


# ──────────────────────────────────────────────
# 4. FŐ — cascade
# ──────────────────────────────────────────────

TOP_LEAGUE_KEYWORDS = [
    "Premier League",
    "La Liga",
    "Primera Division",
    "Bundesliga",
    "Serie A",
    "Ligue 1",
    "Champions League",
    "Europa League",
    "Conference League",
    "Eredivisie",
    "Primeira Liga",
    "Scottish Premiership",
    "Championship",
    "FA Cup",
    "Copa del Rey",
    "DFB Pokal",
    "Coppa Italia",
]


def _is_top_league(league_name: str) -> bool:
    l = (league_name or "").lower()
    return any(k.lower() in l for k in TOP_LEAGUE_KEYWORDS)


def fetch_free_fixtures(date_str: str, top_leagues_only: bool = False) -> list[dict]:
    matches: list[dict] = []

    log.info(f"[FreeFix] SofaScore lekérés: {date_str}")
    matches = fetch_sofascore_day(date_str)

    if len(matches) < 5:
        log.info("[FreeFix] SofaScore kevés eredmény, LiveScore próba...")
        ls_matches = fetch_livescore_day(date_str)
        if len(ls_matches) > len(matches):
            matches = ls_matches

    if len(matches) < 5:
        log.info("[FreeFix] LiveScore is kevés, Flashscore scraping...")
        fs_matches = fetch_flashscore_day(date_str)
        if len(fs_matches) > len(matches):
            matches = fs_matches

    log.info(f"[FreeFix] Összesen {len(matches)} meccs {date_str}-re")

    if top_leagues_only:
        before = len(matches)
        matches = [m for m in matches if _is_top_league(m.get("league_name", ""))]
        log.info(f"[FreeFix] Top liga szűrés: {before} → {len(matches)}")

    enriched = 0
    # Limit to avoid rate limiting: try first 60 matches, with delays
    for m in matches[:60]:
        fid = m.get("fixture_id")
        source = m.get("source", "")
        if fid and source == "sofascore" and not (m.get("odds") or {}).get("1"):
            try:
                odds = fetch_sofascore_odds(int(fid))
                if odds:
                    m["odds"] = odds
                    m["odds_source"] = "sofascore"
                    enriched += 1
                # Small delay to avoid rate limit (SofaScore is lenient but still)
                if enriched > 0 and enriched % 10 == 0:
                    time.sleep(1.5)
            except Exception as e:
                log.debug(f"[FreeFix] Odds enrichment hiba {fid}: {e}")

    if enriched:
        log.info(f"[FreeFix] {enriched} meccshez SofaScore odds beállítva")

    return matches
