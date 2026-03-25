# bot/odds_scraper.py
# 
# ✅ Tippmix ELTÁVOLÍTVA — blokkolja a szerver IP-ket (GitHub Actions-ből sosem működik)
# ✅ Elsődleges forrás: BetExplorer.com (requests + BeautifulSoup, megbízható)
# ✅ Fallback: OddsPortal JSON snippet
# ✅ Ha egyik sem működik: default odds

import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
import os

log = logging.getLogger(__name__)

# TheOddsAPI config
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "acf78bce7a7976c2bc4d028528d4cb2f")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

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
        time.sleep(random.uniform(1.0, 2.5))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.debug(f"HTTP {r.status_code} -> {url}")
    except Exception as e:
        log.debug(f"Fetch failed {url}: {e}")
    return None


# ──────────────────────────────────────────────
# 0. THEODDSAPI — legális JSON API (nem HTML scraping!)
# ──────────────────────────────────────────────

def scrape_theoddsapi(home_team: str, away_team: str, sport: str = "soccer_germany_bundesliga") -> Optional[Dict[str, float]]:
    """
    TheOddsAPI - legális JSON API, nem HTML scraping.
    Sportok: soccer_germany_bundesliga, soccer_epl, soccer_spain_la_liga, stb.
    """
    url = f"{ODDS_API_BASE}/sports/{sport}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",  # 1X2
        "oddsFormat": "decimal",
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            log.debug(f"TheOddsAPI HTTP {r.status_code}")
            return None
        
        data = r.json()
        home_l = home_team.lower().replace(".", "")
        away_l = away_team.lower().replace(".", "")
        
        for event in data:
            event_home = event.get("home_team", "").lower().replace(".", "")
            event_away = event.get("away_team", "").lower().replace(".", "")
            
            # Fuzzy match (min 4 karakter)
            if (home_l[:4] in event_home or event_home[:4] in home_l) and \
               (away_l[:4] in event_away or event_away[:4] in away_l):
                
                bookmakers = event.get("bookmakers", [])
                if not bookmakers:
                    continue
                
                # Használjuk az első bookmaker odds-át
                markets = bookmakers[0].get("markets", [])
                for market in markets:
                    if market.get("key") == "h2h":
                        outcomes = market.get("outcomes", [])
                        if len(outcomes) >= 3:
                            # Keressük meg a home/away/draw odds-okat
                            o1, ox, o2 = None, None, None
                            for outcome in outcomes:
                                name_l = outcome["name"].lower().replace(".", "")
                                price = outcome["price"]
                                
                                if home_l[:4] in name_l or name_l[:4] in home_l:
                                    o1 = price
                                elif away_l[:4] in name_l or name_l[:4] in away_l:
                                    o2 = price
                                elif "draw" in name_l:
                                    ox = price
                            
                            if o1 and o2 and ox:
                                log.info(f"[TheOddsAPI] {home_team} vs {away_team}: 1={o1} X={ox} 2={o2}")
                                return {"1": o1, "X": ox, "2": o2}
    except Exception as e:
        log.debug(f"TheOddsAPI hiba: {e}")
    
    return None


# ──────────────────────────────────────────────
# 1. BETEXPLORER — elsődleges forrás
# requests + BeautifulSoup, nem blokkolja a szervereket
# ──────────────────────────────────────────────

def scrape_betexplorer(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
    """
    BetExplorer.com keresés 1X2 odds-hoz.
    Működik szerver IP-ról is (nem blokkolja).
    """
    query = requests.utils.quote(f"{home_team} {away_team}")
    search_url = f"https://www.betexplorer.com/search/?q={query}"
    html = _get(search_url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.table-main tr, #sortable-1 tr")

        home_l = home_team.lower()
        away_l = away_team.lower()

        for row in rows:
            text = row.get_text(strip=True).lower()
            if home_l[:4] in text and away_l[:4] in text:
                cells = row.select("td")
                if len(cells) >= 4:
                    try:
                        o1 = float(cells[-3].get_text(strip=True).replace(",", "."))
                        ox = float(cells[-2].get_text(strip=True).replace(",", "."))
                        o2 = float(cells[-1].get_text(strip=True).replace(",", "."))
                        if 1.01 <= o1 <= 25 and 1.01 <= ox <= 25 and 1.01 <= o2 <= 25:
                            log.info(f"[BetExplorer] {home_team} vs {away_team}: 1={o1} X={ox} 2={o2}")
                            return {"1": o1, "X": ox, "2": o2}
                    except (ValueError, IndexError):
                        continue

        # Ha keresés nem adott eredményt, próbáljuk a football főoldalt
        football_url = "https://www.betexplorer.com/football/"
        html2 = _get(football_url)
        if html2:
            soup2 = BeautifulSoup(html2, "html.parser")
            rows2 = soup2.select("table.table-main tr")
            for row in rows2:
                text = row.get_text(strip=True).lower()
                if home_l[:4] in text and away_l[:4] in text:
                    cells = row.select("td")
                    if len(cells) >= 4:
                        try:
                            o1 = float(cells[-3].get_text(strip=True).replace(",", "."))
                            ox = float(cells[-2].get_text(strip=True).replace(",", "."))
                            o2 = float(cells[-1].get_text(strip=True).replace(",", "."))
                            if 1.01 <= o1 <= 25:
                                return {"1": o1, "X": ox, "2": o2}
                        except (ValueError, IndexError):
                            continue

    except Exception as e:
        log.debug(f"BetExplorer parse error: {e}")

    return None


# ──────────────────────────────────────────────
# 2. ODDSPORTAL — JSON snippet kinyerés
# ──────────────────────────────────────────────

def scrape_oddsportal(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
    """
    OddsPortal keresés — JSON snippet kinyerés az HTML-ból.
    """
    query = requests.utils.quote(f"{home_team} {away_team}")
    url = f"https://www.oddsportal.com/search/results/{query}/"
    html = _get(url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        home_l = home_team.lower()
        away_l = away_team.lower()

        # Statikus HTML táblázat
        rows = soup.select("div.eventRow, tr.deactivate, div[class*='eventRow']")
        for row in rows:
            text = row.get_text(strip=True).lower()
            if home_l[:4] in text and away_l[:4] in text:
                odds_spans = row.select("span.odds-nowrp, td.odds-nowrp, span[class*='oddsCell']")
                if len(odds_spans) >= 3:
                    try:
                        o1 = float(odds_spans[0].get_text(strip=True))
                        ox = float(odds_spans[1].get_text(strip=True))
                        o2 = float(odds_spans[2].get_text(strip=True))
                        if 1.01 <= o1 <= 25:
                            log.info(f"[OddsPortal] {home_team} vs {away_team}: 1={o1} X={ox} 2={o2}")
                            return {"1": o1, "X": ox, "2": o2}
                    except (ValueError, IndexError):
                        continue

        # JSON sniff a script tagekből
        for script in soup.find_all("script"):
            content = script.string or ""
            if home_l[:4] in content.lower() and "odds" in content.lower():
                match = re.search(
                    r'"home_od":\s*([\d.]+).*?"draw_od":\s*([\d.]+).*?"away_od":\s*([\d.]+)',
                    content,
                )
                if match:
                    o1 = float(match.group(1))
                    ox = float(match.group(2))
                    o2 = float(match.group(3))
                    if 1.01 <= o1 <= 25:
                        return {"1": o1, "X": ox, "2": o2}

    except Exception as e:
        log.debug(f"OddsPortal parse error: {e}")

    return None


# ──────────────────────────────────────────────
# Régi függvénynevek megtartva visszafelé kompatibilitáshoz
# ──────────────────────────────────────────────

def scrape_tippmix_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
    """
    Tippmix helyett BetExplorer-t használunk.
    Függvény neve megtartva a visszafelé kompatibilitás miatt.
    """
    return scrape_betexplorer(home_team, away_team)


def scrape_nemzeti_sport_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
    """
    Nemzeti Sport helyett OddsPortal-t használunk.
    Függvény neve megtartva a visszafelé kompatibilitás miatt.
    """
    return scrape_oddsportal(home_team, away_team)


# ──────────────────────────────────────────────
# FŐ FÜGGVÉNY
# ──────────────────────────────────────────────

def get_odds_with_fallback(home_team: str, away_team: str, sport: str = "soccer_germany_bundesliga") -> Dict[str, float]:
    """
    Próbálja: TheOddsAPI (legális JSON API) -> BetExplorer -> OddsPortal -> default fallback.
    Sosem dob exception, mindig visszaad valamit.
    """
    # 1. TheOddsAPI (legális JSON API, nem HTML scraping!)
    try:
        odds = scrape_theoddsapi(home_team, away_team, sport)
        if odds:
            print(f"[SCRAPED] {home_team} vs {away_team} -> TheOddsAPI: {odds}")
            return odds
    except Exception as e:
        log.debug(f"TheOddsAPI hiba: {e}")

    # 2. BetExplorer (HTML scraping, fallback)
    try:
        odds = scrape_betexplorer(home_team, away_team)
        if odds:
            print(f"[SCRAPED] {home_team} vs {away_team} -> BetExplorer: {odds}")
            return odds
    except Exception as e:
        log.debug(f"BetExplorer hiba: {e}")

    # 3. OddsPortal (HTML scraping, másodlagos fallback)
    try:
        odds = scrape_oddsportal(home_team, away_team)
        if odds:
            print(f"[SCRAPED] {home_team} vs {away_team} -> OddsPortal: {odds}")
            return odds
    except Exception as e:
        log.debug(f"OddsPortal hiba: {e}")

    # 4. Default fallback — sosem dob hibát
    print(f"[SCRAPED] {home_team} vs {away_team} -> fallback default odds")
    return {
        "1": 1.85,
        "X": 3.40,
        "2": 4.20,
    }


if __name__ == "__main__":
    test_odds = get_odds_with_fallback("RB Leipzig", "Hoffenheim")
    print(f"Odds: {test_odds}")
