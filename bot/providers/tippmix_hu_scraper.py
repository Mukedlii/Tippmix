"""
bot/providers/tippmix_hu_scraper.py

Tippmix.hu + TippmixPro.hu odds scraper — MAGYAR BUKMÉKERI ODDS

MIT AD:
  - Mai meccsek oddsai (1X2, Over/Under, DNB)
  - Tippmix.hu: Magyar állami fogadóiroda
  - TippmixPro.hu: Prémium verzió
  - Meccs időpontok, csapatnevek magyarul

FONTOS:
  - Ez csak az ODDS scraping — a meccsek listájához más forrás kell
  - Az odds adatokat a bot majd összeveti a Poisson becsléssel
  - Ha az odds > Poisson becslés → VALUE fogadás (ajánlott)

BEÁLLÍTÁS: Nincs szükség API kulcsra — nyilvános weboldalak.
"""

from __future__ import annotations

import re
import time
import json
import logging
import random
from typing import Any, Dict, List, Optional
from datetime import datetime, date

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.tippmixpro.hu/",
}

TIPPMIXPRO_BASE = "https://www.tippmixpro.hu"
TIPPMIX_BASE = "https://www.tippmix.hu"


def _get(url: str, timeout: int = 20) -> Optional[str]:
    try:
        time.sleep(random.uniform(2.0, 3.5))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.warning(f"HTTP {r.status_code}: {url}")
    except Exception as e:
        log.error(f"Fetch hiba {url}: {e}")
    return None


def _get_json(url: str, timeout: int = 15) -> Optional[Any]:
    try:
        time.sleep(random.uniform(1.5, 2.5))
        h = dict(HEADERS)
        h["Accept"] = "application/json, text/javascript, */*"
        r = requests.get(url, headers=h, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        log.warning(f"JSON HTTP {r.status_code}: {url}")
    except Exception as e:
        log.error(f"JSON fetch hiba {url}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────
# TippmixPro.hu scraper
# ─────────────────────────────────────────────────────────────────

def scrape_tippmixpro_today() -> List[Dict[str, Any]]:
    """
    TippmixPro.hu mai focimeccsek oddsainak letöltése.

    TippmixPro JSON API-t használ a frontend mögött,
    ez a publikusan hozzáférhető endpointot tárja fel.
    """
    results = []

    # TippmixPro JSON API endpoint (publikus, nem kell auth)
    today_str = date.today().strftime("%Y-%m-%d")

    # Próbálja a beágyazott JSON API-t
    api_urls = [
        f"{TIPPMIXPRO_BASE}/api/v1/events?date={today_str}&sport=soccer",
        f"{TIPPMIXPRO_BASE}/events?date={today_str}&sport=1",
        f"{TIPPMIXPRO_BASE}/api/events/today",
    ]

    for api_url in api_urls:
        data = _get_json(api_url)
        if data:
            parsed = _parse_tippmixpro_api(data)
            if parsed:
                log.info(f"TippmixPro API OK: {len(parsed)} meccs ({api_url})")
                return parsed

    # Fallback: HTML scraping
    html_url = f"{TIPPMIXPRO_BASE}/sportok/labdarugas"
    html = _get(html_url)
    if html:
        return _parse_tippmixpro_html(html)

    log.warning("TippmixPro: nem sikerült adatot lekérni")
    return []


def _parse_tippmixpro_api(data: Any) -> List[Dict[str, Any]]:
    """TippmixPro API válasz feldolgozása."""
    if not isinstance(data, (list, dict)):
        return []

    events = data if isinstance(data, list) else data.get("events", data.get("data", []))
    results = []

    for event in (events or []):
        try:
            home = event.get("home_team") or event.get("homeTeam") or event.get("home")
            away = event.get("away_team") or event.get("awayTeam") or event.get("away")
            if not home or not away:
                continue

            odds_raw = event.get("odds", event.get("markets", {}))
            odds_1 = odds_x = odds_2 = None

            if isinstance(odds_raw, dict):
                odds_1 = odds_raw.get("1") or odds_raw.get("home") or odds_raw.get("1x2_home")
                odds_x = odds_raw.get("X") or odds_raw.get("draw") or odds_raw.get("1x2_draw")
                odds_2 = odds_raw.get("2") or odds_raw.get("away") or odds_raw.get("1x2_away")
            elif isinstance(odds_raw, list) and len(odds_raw) >= 3:
                odds_1, odds_x, odds_2 = odds_raw[0], odds_raw[1], odds_raw[2]

            kickoff = event.get("start_time") or event.get("kickoff") or event.get("date", "")

            results.append({
                "home_team": str(home).strip(),
                "away_team": str(away).strip(),
                "odds_1": float(odds_1) if odds_1 else None,
                "odds_x": float(odds_x) if odds_x else None,
                "odds_2": float(odds_2) if odds_2 else None,
                "kickoff": str(kickoff)[:16],
                "league": event.get("league") or event.get("competition", ""),
                "source": "TippmixPro",
            })
        except Exception as e:
            log.debug(f"Event parse hiba: {e}")

    return results


def _parse_tippmixpro_html(html: str) -> List[Dict[str, Any]]:
    """TippmixPro HTML scraping fallback."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Általános mérkőzés-kártya keresés
    event_containers = soup.find_all(["div", "tr", "article"], class_=re.compile(
        r"event|match|game|merkozés|esem[eé]ny", re.I
    ))

    for container in event_containers[:50]:
        try:
            text = container.get_text(separator=" ", strip=True)

            # Csapatneveket keres: "Team A - Team B" vagy "Team A vs Team B"
            vs_match = re.search(r"(.+?)\s+[-–—vsVS]+\s+(.+?)(?:\s+\d|\s*$)", text)
            if not vs_match:
                continue

            home = vs_match.group(1).strip()
            away = vs_match.group(2).strip()

            if len(home) < 2 or len(away) < 2:
                continue

            # Odds keresés (decimális formátum: 1.xx - 9.xx)
            odds_vals = re.findall(r"\b([1-9]\.\d{2})\b", text)
            odds_1 = odds_x = odds_2 = None
            if len(odds_vals) >= 3:
                odds_1 = float(odds_vals[0])
                odds_x = float(odds_vals[1])
                odds_2 = float(odds_vals[2])

            results.append({
                "home_team": home,
                "away_team": away,
                "odds_1": odds_1,
                "odds_x": odds_x,
                "odds_2": odds_2,
                "kickoff": "",
                "source": "TippmixPro_HTML",
            })
        except Exception:
            pass

    log.info(f"TippmixPro HTML: {len(results)} meccs kinyerve")
    return results


# ─────────────────────────────────────────────────────────────────
# OddsPortal.hu / international odds
# ─────────────────────────────────────────────────────────────────

def scrape_oddsportal_football(days_ahead: int = 1) -> List[Dict[str, Any]]:
    """
    OddsPortal.com focimeccsek + legjobb odds több bukmékertől.

    Az OddsPortal az egyik legjobb ingyenes odds-aggregátor.
    Nem kell regisztráció, nyilvános adat.
    """
    results = []
    today = date.today()

    leagues_to_scrape = [
        ("england/premier-league", "Premier League", "England"),
        ("germany/bundesliga", "Bundesliga", "Germany"),
        ("spain/laliga", "La Liga", "Spain"),
        ("italy/serie-a", "Serie A", "Italy"),
        ("france/ligue-1", "Ligue 1", "France"),
        ("netherlands/eredivisie", "Eredivisie", "Netherlands"),
        ("portugal/primeira-liga", "Primeira Liga", "Portugal"),
        ("hungary/otp-bank-liga", "OTP Bank Liga", "Hungary"),
    ]

    for league_path, league_name, country in leagues_to_scrape:
        url = f"https://www.oddsportal.com/football/{league_path}/results/"
        html = _get(url)
        if not html:
            continue

        matches = _parse_oddsportal_page(html, league_name, country)
        results.extend(matches)

        if matches:
            print(f"[OddsPortal] {league_name}: {len(matches)} meccs")
        time.sleep(random.uniform(3.0, 5.0))

    return results


def _parse_oddsportal_page(html: str, league_name: str, country: str) -> List[Dict[str, Any]]:
    """OddsPortal HTML oldal feldolgozása."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # OddsPortal React-alapú, JSON adatot tartalmaz az oldalon
    scripts = soup.find_all("script")
    for script in scripts:
        txt = script.get_text() if script.string is None else script.string
        if txt and "oddsdata" in txt.lower():
            # Próbáljuk kinyerni a beágyazott JSON-t
            json_match = re.search(r"oddsdata\s*=\s*(\{.+?\});", txt, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    for key, match_data in data.items():
                        home = match_data.get("home-name", "")
                        away = match_data.get("away-name", "")
                        if home and away:
                            results.append({
                                "home_team": home,
                                "away_team": away,
                                "league_name": league_name,
                                "country_name": country,
                                "source": "OddsPortal",
                            })
                except Exception:
                    pass

    # HTML fallback
    if not results:
        table_rows = soup.find_all("tr", class_=re.compile(r"deactivate|odd|even", re.I))
        for row in table_rows[:30]:
            try:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                match_cell = cells[1] if len(cells) > 1 else cells[0]
                teams_text = match_cell.get_text(strip=True)
                if " - " in teams_text:
                    parts = teams_text.split(" - ", 1)
                    home, away = parts[0].strip(), parts[1].strip()
                    if home and away and len(home) > 2:
                        # Odds kinyerése
                        odds_cells = [c.get_text(strip=True) for c in cells[2:5]]
                        odds_vals = []
                        for oc in odds_cells:
                            try:
                                odds_vals.append(float(oc))
                            except Exception:
                                pass

                        results.append({
                            "home_team": home,
                            "away_team": away,
                            "odds_1": odds_vals[0] if len(odds_vals) > 0 else None,
                            "odds_x": odds_vals[1] if len(odds_vals) > 1 else None,
                            "odds_2": odds_vals[2] if len(odds_vals) > 2 else None,
                            "league_name": league_name,
                            "country_name": country,
                            "source": "OddsPortal",
                        })
            except Exception:
                pass

    return results


# ─────────────────────────────────────────────────────────────────
# Összesítő függvény
# ─────────────────────────────────────────────────────────────────

def get_all_odds_for_today() -> List[Dict[str, Any]]:
    """
    Összegyűjti az összes mai meccs oddsát minden forrásból.

    Prioritás: TippmixPro > OddsPortal > TheOddsAPI (ha van kulcs)
    """
    all_odds = []

    print("[ODDS] TippmixPro.hu scraping...")
    tippmix_odds = scrape_tippmixpro_today()
    all_odds.extend(tippmix_odds)
    print(f"[ODDS] TippmixPro: {len(tippmix_odds)} meccs")

    print("[ODDS] OddsPortal scraping...")
    oddsportal_odds = scrape_oddsportal_football()
    all_odds.extend(oddsportal_odds)
    print(f"[ODDS] OddsPortal: {len(oddsportal_odds)} meccs")

    print(f"[ODDS] Összesen: {len(all_odds)} meccs odds")
    return all_odds


def find_odds_for_match(
    home_team: str,
    away_team: str,
    all_odds: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Megkeres egy meccshez tartozó oddsot a gyűjtött listából.

    Fuzzy matching: részleges névegyezés is elfogadott.
    """
    if all_odds is None:
        all_odds = get_all_odds_for_today()

    home_lower = home_team.lower()
    away_lower = away_team.lower()

    best_match = None
    best_score = 0.0

    for odds_entry in all_odds:
        entry_home = (odds_entry.get("home_team") or "").lower()
        entry_away = (odds_entry.get("away_team") or "").lower()

        # Pontozás: hány szóban egyezik
        score = 0.0
        for word in home_lower.split():
            if len(word) > 2 and word in entry_home:
                score += 1.0
        for word in away_lower.split():
            if len(word) > 2 and word in entry_away:
                score += 1.0

        if score > best_score:
            best_score = score
            best_match = odds_entry

    if best_score >= 2.0:
        return best_match
    return None


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    odds = get_all_odds_for_today()
    print(f"\nÖsszegyűjtött odds: {len(odds)} meccs")
    for o in odds[:10]:
        print(f"  {o['home_team']} vs {o['away_team']}: "
              f"1={o.get('odds_1')}, X={o.get('odds_x')}, 2={o.get('odds_2')}")
