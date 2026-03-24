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

log = logging.getLogger(**name**)

HEADERS = {
“User-Agent”: (
“Mozilla/5.0 (Windows NT 10.0; Win64; x64) “
“AppleWebKit/537.36 (KHTML, like Gecko) “
“Chrome/122.0.0.0 Safari/537.36”
),
“Accept-Language”: “en-US,en;q=0.9”,
“Accept”: “text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8”,
“Referer”: “https://www.google.com/”,
}

def _get(url: str, timeout: int = 15) -> Optional[str]:
try:
time.sleep(random.uniform(1.0, 2.5))
r = requests.get(url, headers=HEADERS, timeout=timeout)
if r.status_code == 200:
return r.text
log.debug(f”HTTP {r.status_code} -> {url}”)
except Exception as e:
log.debug(f”Fetch failed {url}: {e}”)
return None

# ──────────────────────────────────────────────

# 1. BETEXPLORER — elsődleges forrás

# requests + BeautifulSoup, nem blokkolja a szervereket

# ──────────────────────────────────────────────

def scrape_betexplorer(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
“””
BetExplorer.com keresés 1X2 odds-hoz.
Mukodik szerver IP-rol is (nem blokkolja).
“””
query = requests.utils.quote(f”{home_team} {away_team}”)
search_url = f”https://www.betexplorer.com/search/?q={query}”
html = _get(search_url)
if not html:
return None

```
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

    # Ha kereses nem adott eredmenyt, probaljuk a football fooldalt
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
```

# ──────────────────────────────────────────────

# 2. ODDSPORTAL — JSON snippet kinyeres

# ──────────────────────────────────────────────

def scrape_oddsportal(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
“””
OddsPortal kereses — JSON snippet kinyeres az HTML-bol.
“””
query = requests.utils.quote(f”{home_team} {away_team}”)
url = f”https://www.oddsportal.com/search/results/{query}/”
html = _get(url)
if not html:
return None

```
try:
    soup = BeautifulSoup(html, "html.parser")
    home_l = home_team.lower()
    away_l = away_team.lower()

    # Statikus HTML tablazat
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

    # JSON sniff a script tagekbol
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
```

# ──────────────────────────────────────────────

# Regi fuggvenynevek megtartva visszafele kompatibilitashoz

# ──────────────────────────────────────────────

def scrape_tippmix_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
“””
Tippmix helyett BetExplorer-t hasznalunk.
Fuggveny neve megtartva a visszafele kompatibilitas miatt.
“””
return scrape_betexplorer(home_team, away_team)

def scrape_nemzeti_sport_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
“””
Nemzeti Sport helyett OddsPortal-t hasznalunk.
Fuggveny neve megtartva a visszafele kompatibilitas miatt.
“””
return scrape_oddsportal(home_team, away_team)

# ──────────────────────────────────────────────

# FO FUGGVENY

# ──────────────────────────────────────────────

def get_odds_with_fallback(home_team: str, away_team: str) -> Dict[str, float]:
“””
Probaja: BetExplorer -> OddsPortal -> default fallback.
Sosem dob exception, mindig visszaad valamit.
“””
# 1. BetExplorer (elsodleges, megbizhato)
try:
odds = scrape_betexplorer(home_team, away_team)
if odds:
print(f”[SCRAPED] {home_team} vs {away_team} -> BetExplorer: {odds}”)
return odds
except Exception as e:
log.debug(f”BetExplorer hiba: {e}”)

```
# 2. OddsPortal (masodlagos)
try:
    odds = scrape_oddsportal(home_team, away_team)
    if odds:
        print(f"[SCRAPED] {home_team} vs {away_team} -> OddsPortal: {odds}")
        return odds
except Exception as e:
    log.debug(f"OddsPortal hiba: {e}")

# 3. Default fallback — sosem dob hibat
print(f"[SCRAPED] {home_team} vs {away_team} -> fallback default odds")
return {
    "1": 1.85,
    "X": 3.40,
    "2": 4.20,
}
```

if **name** == “**main**”:
test_odds = get_odds_with_fallback(“RB Leipzig”, “Hoffenheim”)
print(f”Odds: {test_odds}”)
