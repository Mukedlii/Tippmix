"""
bot/providers/injuries.py

Sérülések és eltiltások lekérése kizárólag ingyenes forrásokból.

Források:
  1. FBref.com scraping (ingyenes)
  2. Transfermarkt scraping (ingyenes)
  3. ESPN soccernet (ingyenes)

Használat:
  injuries = get_team_injuries("Arsenal", "Premier League")
  → [{"player": "Saka", "type": "injury", "reason": "hamstring", "expected_return": "2026-03-25"}]
"""

from __future__ import annotations

import os
import re
import time
import random
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

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
}


def _get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        time.sleep(random.uniform(0.8, 1.5))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.debug(f"HTTP {r.status_code} → {url}")
    except Exception as e:
        log.debug(f"Fetch failed {url}: {e}")
    return None


# ───────────────────────────────────────────
# 2. FBREF - Free scraping
# ───────────────────────────────────────────

def search_fbref_team_url(team_name: str) -> Optional[str]:
    """FBref csapat URL keresése."""
    url = f"https://fbref.com/search/search.fcgi?search={requests.utils.quote(team_name)}"
    html = _get(url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        link = soup.select_one("div.search-item-name a[href*='/squads/']")
        if link:
            return "https://fbref.com" + link["href"]
    except Exception as e:
        log.debug(f"FBref search error: {e}")

    return None


def fetch_fbref_injuries(team_name: str) -> List[Dict[str, Any]]:
    """
    FBref injury/suspension table scraping.
    Sajnos az FBref nem mindig mutatja a sérülteket prominеnsen,
    de van egy "Squad & Position" tab ahol szerepelhet.
    """
    team_url = search_fbref_team_url(team_name)
    if not team_url:
        return []

    html = _get(team_url)
    if not html:
        return []

    injuries = []
    try:
        soup = BeautifulSoup(html, "html.parser")

        # FBref néha van injury note column
        tables = soup.select("table")
        for table in tables:
            rows = table.select("tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) < 3:
                    continue

                # Keresünk injury mention
                row_text = row.get_text(strip=True).lower()
                if "injury" in row_text or "suspended" in row_text:
                    player_cell = row.select_one("th a, td a")
                    player = player_cell.get_text(strip=True) if player_cell else "Unknown"

                    injuries.append({
                        "player": player,
                        "type": "injury" if "injury" in row_text else "suspension",
                        "reason": row_text[:50],
                        "expected_return": None,
                        "source": "fbref",
                    })

    except Exception as e:
        log.debug(f"FBref injuries parse error: {e}")

    return injuries


# ───────────────────────────────────────────
# 3. TRANSFERMARKT - Ingyenes, de rate-limited
# ───────────────────────────────────────────

def search_transfermarkt_team(team_name: str) -> Optional[str]:
    """Transfermarkt csapat oldal keresése."""
    # Transfermarkt search rate-limitált, egyszerű match URL pattern alapon
    # Példa: Manchester United → /manchester-united/startseite/verein/985
    team_slug = team_name.lower().replace(" ", "-").replace(".", "")

    # Best-effort próba (nem garantált)
    url = f"https://www.transfermarkt.com/{team_slug}/startseite/verein/"
    html = _get(url)
    if html and "verein" in html.lower():
        return url

    return None


def fetch_transfermarkt_injuries(team_name: str) -> List[Dict[str, Any]]:
    """
    Transfermarkt injuries page scraping.
    Példa URL: https://www.transfermarkt.com/manchester-united/sperrenundverletzungen/verein/985
    """
    team_url = search_transfermarkt_team(team_name)
    if not team_url:
        return []

    # Átalakítjuk injuries URL-re
    injury_url = team_url.replace("/startseite/", "/sperrenundverletzungen/")
    html = _get(injury_url)
    if not html:
        return []

    injuries = []
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Transfermarkt injury table: player name, injury type, expected return
        table = soup.select_one("table.items")
        if not table:
            return []

        rows = table.select("tr")[1:]  # skip header
        for row in rows:
            player_cell = row.select_one("td.hauptlink a")
            injury_cell = row.select_one("td.hauptlink + td")
            return_cell = row.select_one("td:nth-of-type(4)")

            if not player_cell:
                continue

            player = player_cell.get_text(strip=True)
            injury_reason = injury_cell.get_text(strip=True) if injury_cell else ""
            expected_return = return_cell.get_text(strip=True) if return_cell else None

            injuries.append({
                "player": player,
                "type": "suspension" if "Sperre" in injury_reason else "injury",
                "reason": injury_reason,
                "expected_return": expected_return,
                "source": "transfermarkt",
            })

    except Exception as e:
        log.debug(f"Transfermarkt parse error: {e}")

    return injuries


# ───────────────────────────────────────────
# 4. ESPN SOCCERNET - Ingyenes, könnyű scraping
# ───────────────────────────────────────────

def fetch_espn_injuries(team_name: str, league_hint: str = "") -> List[Dict[str, Any]]:
    """
    ESPN Soccernet injuries scraping.
    Példa: https://www.espn.com/soccer/team/injuries/_/id/359/liverpool
    """
    # ESPN team ID mapping (top teams only)
    ESPN_TEAMS = {
        "arsenal": 359,
        "liverpool": 364,
        "manchester city": 382,
        "manchester united": 360,
        "chelsea": 363,
        "tottenham": 367,
        # ... add more as needed
    }

    team_key = team_name.lower()
    team_id = ESPN_TEAMS.get(team_key)
    if not team_id:
        log.debug(f"ESPN team ID not mapped: {team_name}")
        return []

    url = f"https://www.espn.com/soccer/team/injuries/_/id/{team_id}"
    html = _get(url)
    if not html:
        return []

    injuries = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("tr.Table__TR")

        for row in rows:
            player_cell = row.select_one("td a")
            status_cell = row.select_one("td:nth-of-type(2)")
            reason_cell = row.select_one("td:nth-of-type(3)")
            return_cell = row.select_one("td:nth-of-type(4)")

            if not player_cell:
                continue

            player = player_cell.get_text(strip=True)
            status = status_cell.get_text(strip=True) if status_cell else ""
            reason = reason_cell.get_text(strip=True) if reason_cell else ""
            expected_return = return_cell.get_text(strip=True) if return_cell else None

            injuries.append({
                "player": player,
                "type": "suspension" if "suspended" in status.lower() else "injury",
                "reason": reason,
                "expected_return": expected_return,
                "source": "espn",
            })

    except Exception as e:
        log.debug(f"ESPN injuries parse error: {e}")

    return injuries


# ───────────────────────────────────────────
# 5. FŐ FÜGGVÉNY - Multi-source aggregáció
# ───────────────────────────────────────────

def get_team_injuries(
    team_name: str,
    league_name: str = "",
    team_id: Optional[int] = None,
    season: int = 2024,
) -> List[Dict[str, Any]]:
    """
    Sérülések és eltiltások lekérése több forrásból.

    Args:
        team_name: Csapat neve
        league_name: Liga neve (kontextus)
        team_id: (nem használt, csak kompatibilitás miatt)
        season: Szezon év

    Returns:
        List of injuries: [{"player": "Saka", "type": "injury", "reason": "hamstring", ...}]
    """
    all_injuries: List[Dict[str, Any]] = []

    # FBref scraping (ingyenes)
    fbref_injuries = fetch_fbref_injuries(team_name)
    all_injuries.extend(fbref_injuries)
    if fbref_injuries:
        log.info(f"[Injuries] FBref: {team_name} → {len(fbref_injuries)} found")

    # 3. Transfermarkt scraping (opcionális, lassú lehet)
    if not all_injuries:  # csak ha eddig semmi
        tm_injuries = fetch_transfermarkt_injuries(team_name)
        all_injuries.extend(tm_injuries)
        if tm_injuries:
            log.info(f"[Injuries] Transfermarkt: {team_name} → {len(tm_injuries)} found")

    # 4. ESPN (top teams only)
    if not all_injuries:
        espn_injuries = fetch_espn_injuries(team_name, league_name)
        all_injuries.extend(espn_injuries)
        if espn_injuries:
            log.info(f"[Injuries] ESPN: {team_name} → {len(espn_injuries)} found")

    # Deduplikáció player név alapján
    seen = set()
    unique = []
    for inj in all_injuries:
        key = inj["player"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(inj)

    return unique


def format_injuries_for_prompt(injuries: List[Dict[str, Any]], team_name: str) -> str:
    """
    Formázott injury info AI prompt-hoz.
    """
    if not injuries:
        return ""

    lines = [f"⚕️ SÉRÜLÉSEK/ELTILTÁSOK ({team_name}):"]

    for inj in injuries:
        player = inj["player"]
        itype = inj["type"]
        reason = inj.get("reason", "")
        ret = inj.get("expected_return")

        if itype == "suspension":
            lines.append(f"  ⛔ {player} - ELTILTVA ({reason})")
        else:
            ret_str = f" (vissza: {ret})" if ret else ""
            lines.append(f"  🏥 {player} - {reason}{ret_str}")

    if len(injuries) >= 3:
        lines.append(f"  ⚠️ {len(injuries)} kulcsjátékos hiányzik → gyengébb csapat!")

    return "\n".join(lines)
