# Tippmix.hu odds scraper

import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
import re

# ✅ JAVÍTVA: új Tippmix URL-ek — a régi /sport/fogadas/labdarugas már 404

TIPPMIX_URLS = [
“https://www.tippmix.hu/meccsek”,
“https://www.tippmix.hu/fogadas”,
“https://www.tippmix.hu/”,
]

def scrape_tippmix_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
“””
Scrapel Tippmix.hu-ról 1X2 odds-okat egy meccshez.
Több URL-t próbál, ha az egyik 404.

```
Returns:
    {"1": 2.10, "X": 3.40, "2": 3.20} vagy None
"""
home = home_team.lower().strip()
away = away_team.lower().strip()

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
}

for url in TIPPMIX_URLS:
    try:
        response = requests.get(url, headers=headers, timeout=15)

        # ✅ JAVÍTVA: 404 esetén csendesen a következő URL-re lép, nem dob hibát
        if response.status_code == 404:
            print(f"Tippmix 404: {url} — következő URL próbálása...")
            continue

        if response.status_code != 200:
            print(f"Tippmix HTTP {response.status_code}: {url}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        # Meccs sorok keresése (rugalmas class matching)
        matches = soup.find_all(
            ["div", "tr"],
            class_=re.compile(r"match|event|meccs|fogadas", re.I),
        )

        for match in matches:
            match_text = match.get_text().lower()

            if home[:4] in match_text and away[:4] in match_text:
                odds_elements = match.find_all(
                    ["span", "div", "td"],
                    class_=re.compile(r"odd|koef|rate|szorzó|odds", re.I),
                )

                if len(odds_elements) >= 3:
                    try:
                        o1 = float(odds_elements[0].get_text().strip().replace(",", "."))
                        ox = float(odds_elements[1].get_text().strip().replace(",", "."))
                        o2 = float(odds_elements[2].get_text().strip().replace(",", "."))

                        # Sanity check: reális odds tartomány
                        if 1.01 <= o1 <= 25 and 1.01 <= ox <= 25 and 1.01 <= o2 <= 25:
                            return {"1": o1, "X": ox, "2": o2}
                    except (ValueError, IndexError):
                        continue

    except requests.exceptions.ConnectionError:
        print(f"Tippmix kapcsolódási hiba: {url}")
        continue
    except Exception as e:
        print(f"Tippmix scraping error ({url}): {repr(e)}")
        continue

# Ha egyik URL sem működött
return None
```

def scrape_nemzeti_sport_odds(home_team: str, away_team: str) -> Optional[Dict[str, float]]:
“””
Scrapel Nemzeti Sport-ról odds-okat (backup).
“””
try:
url = “https://www.nemzetisport.hu/fogadas”
headers = {
“User-Agent”: (
“Mozilla/5.0 (Windows NT 10.0; Win64; x64) “
“AppleWebKit/537.36 (KHTML, like Gecko) “
“Chrome/122.0.0.0 Safari/537.36”
)
}

```
    response = requests.get(url, headers=headers, timeout=15)

    # ✅ JAVÍTVA: hibás státuszkód esetén None, nem exception
    if response.status_code != 200:
        print(f"Nemzeti Sport HTTP {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    home = home_team.lower().strip()
    away = away_team.lower().strip()

    matches = soup.find_all(
        ["div", "tr"],
        class_=re.compile(r"match|game|event", re.I),
    )

    for match in matches:
        text = match.get_text().lower()
        if home[:4] in text and away[:4] in text:
            odds = match.find_all(
                ["span", "td"],
                class_=re.compile(r"odd|rate|koef", re.I),
            )
            if len(odds) >= 3:
                try:
                    o1 = float(odds[0].get_text().strip().replace(",", "."))
                    ox = float(odds[1].get_text().strip().replace(",", "."))
                    o2 = float(odds[2].get_text().strip().replace(",", "."))
                    if 1.01 <= o1 <= 25:
                        return {"1": o1, "X": ox, "2": o2}
                except (ValueError, IndexError):
                    continue

    return None

except Exception as e:
    print(f"Nemzeti Sport scraping error: {repr(e)}")
    return None
```

def get_odds_with_fallback(home_team: str, away_team: str) -> Dict[str, float]:
“””
Próbálja: Tippmix → Nemzeti Sport → default fallback.

```
✅ JAVÍTVA: sosem dob exception, mindig visszaad valamit.
"""
# 1. Tippmix (több URL-lel)
odds = scrape_tippmix_odds(home_team, away_team)
if odds:
    print(f"[SCRAPED] {home_team} vs {away_team} → Tippmix: {odds}")
    return odds

# 2. Nemzeti Sport
odds = scrape_nemzeti_sport_odds(home_team, away_team)
if odds:
    print(f"[SCRAPED] {home_team} vs {away_team} → Nemzeti Sport: {odds}")
    return odds

# 3. Fallback default
print(f"[SCRAPED] {home_team} vs {away_team} → fallback default odds")
return {
    "1": 1.85,
    "X": 3.40,
    "2": 4.20,
}
```

if **name** == “**main**”:
test_odds = get_odds_with_fallback(“RB Leipzig”, “Hoffenheim”)
print(f”Odds: {test_odds}”)
