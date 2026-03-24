“””
bot/providers/playwright_odds_scraper.py

Playwright-alapú odds scraper — JavaScript oldalakhoz.
Működik: OddsPortal, BettingExpert, Flashscore

Telepítés (requirements.txt-be add hozzá):
playwright>=1.40.0

GitHub Actions-ben a workflow-ba add hozzá:
- name: Install Playwright browsers
run: playwright install chromium –with-deps
“””

from **future** import annotations

import logging
import os
import re
import time
from typing import Optional

log = logging.getLogger(**name**)

# —————————————————————————

# Lazy import — csak ha tényleg kell

# —————————————————————————

def _get_playwright():
try:
from playwright.sync_api import sync_playwright
return sync_playwright
except ImportError:
log.warning(“Playwright nincs telepítve! Futtasd: pip install playwright && playwright install chromium”)
return None

# —————————————————————————

# Közös browser indítás

# —————————————————————————

def _launch_browser(playwright):
return playwright.chromium.launch(
headless=True,
args=[
“–no-sandbox”,
“–disable-setuid-sandbox”,
“–disable-dev-shm-usage”,
“–disable-gpu”,
],
)

def _new_page(browser, timeout: int = 60000):  # ✅ JAVÍTVA: 30000 → 60000
ctx = browser.new_context(
user_agent=(
“Mozilla/5.0 (Windows NT 10.0; Win64; x64) “
“AppleWebKit/537.36 (KHTML, like Gecko) “
“Chrome/122.0.0.0 Safari/537.36”
),
locale=“en-US”,
viewport={“width”: 1280, “height”: 900},
)
page = ctx.new_page()
page.set_default_timeout(timeout)
return page

# —————————————————————————

# 1. ODDSPORTAL

# —————————————————————————

def scrape_oddsportal(home_team: str, away_team: str) -> Optional[dict]:
“”“OddsPortal.com Playwright scraper.”””
sync_playwright = _get_playwright()
if not sync_playwright:
return None

```
try:
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = _new_page(browser)

        query = f"{home_team} {away_team}"
        url = f"https://www.oddsportal.com/search/results/{query}/"
        log.info(f"[OddsPortal] Fetching: {url}")

        page.goto(url, wait_until="domcontentloaded", timeout=60000)  # ✅ JAVÍTVA
        page.wait_for_timeout(3000)

        rows = page.query_selector_all("div.eventRow, div[class*='eventRow']")

        for row in rows:
            text = (row.inner_text() or "").lower()
            if home_team.lower()[:4] in text or away_team.lower()[:4] in text:
                odds_els = row.query_selector_all("div[class*='odds'], span[class*='odds']")
                odds_vals = []
                for el in odds_els:
                    try:
                        val = float(el.inner_text().strip())
                        if 1.01 <= val <= 25:
                            odds_vals.append(val)
                    except Exception:
                        continue

                if len(odds_vals) >= 3:
                    browser.close()
                    return {
                        "source": "oddsportal",
                        "odds_1": odds_vals[0],
                        "odds_x": odds_vals[1],
                        "odds_2": odds_vals[2],
                    }

        page.goto("https://www.oddsportal.com/football/", wait_until="domcontentloaded", timeout=60000)  # ✅ JAVÍTVA
        page.wait_for_timeout(3000)

        rows = page.query_selector_all("div.eventRow, div[class*='eventRow']")
        for row in rows:
            text = (row.inner_text() or "").lower()
            if home_team.lower()[:4] in text and away_team.lower()[:4] in text:
                odds_els = row.query_selector_all("div[class*='odds'], span[class*='odds'], p[class*='height']")
                odds_vals = []
                for el in odds_els:
                    try:
                        val = float(el.inner_text().strip())
                        if 1.01 <= val <= 25:
                            odds_vals.append(val)
                    except Exception:
                        continue

                if len(odds_vals) >= 3:
                    browser.close()
                    return {
                        "source": "oddsportal",
                        "odds_1": odds_vals[0],
                        "odds_x": odds_vals[1],
                        "odds_2": odds_vals[2],
                    }

        browser.close()

except Exception as e:
    log.warning(f"[OddsPortal] Hiba: {e}")

return None
```

# —————————————————————————

# 2. BETTINGEXPERT  ✅ JAVÍTVA: networkidle → domcontentloaded + timeout

# —————————————————————————

def scrape_bettingexpert(home_team: str, away_team: str) -> Optional[dict]:
“”“BettingExpert.com Playwright scraper — tipster consensus + odds.”””
sync_playwright = _get_playwright()
if not sync_playwright:
return None

```
try:
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = _new_page(browser, timeout=60000)  # ✅ JAVÍTVA

        url = "https://www.bettingexpert.com/tips/football"
        log.info(f"[BettingExpert] Fetching: {url}")

        # ✅ JAVÍTVA: networkidle → domcontentloaded, timeout=60000
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        page.wait_for_timeout(2000)

        home_l = home_team.lower()
        away_l = away_team.lower()

        tip_rows = page.query_selector_all("article, div[class*='tip'], div[class*='pick'], tr[class*='tip']")

        for row in tip_rows:
            text = (row.inner_text() or "").lower()
            if home_l[:4] in text and away_l[:4] in text:
                odds_els = row.query_selector_all("[class*='odd'], [class*='price'], [class*='coeff']")
                for el in odds_els:
                    try:
                        val = float(el.inner_text().strip())
                        if 1.01 <= val <= 25:
                            browser.close()
                            return {
                                "source": "bettingexpert",
                                "odds_tip": val,
                            }
                    except Exception:
                        continue

        browser.close()

except Exception as e:
    log.warning(f"[BettingExpert] Hiba: {e}")

return None
```

# —————————————————————————

# 3. FLASHSCORE

# —————————————————————————

def scrape_flashscore(home_team: str, away_team: str) -> Optional[dict]:
“”“Flashscore.com Playwright scraper.”””
sync_playwright = _get_playwright()
if not sync_playwright:
return None

```
try:
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = _new_page(browser)

        search_url = f"https://www.flashscore.com/search/?q={home_team}"
        log.info(f"[Flashscore] Fetching: {search_url}")

        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)  # ✅ JAVÍTVA
        page.wait_for_timeout(3000)

        results = page.query_selector_all("div.search__result, a[class*='searchResult']")

        match_url = None
        for result in results:
            text = (result.inner_text() or "").lower()
            if home_team.lower()[:4] in text and away_team.lower()[:4] in text:
                link = result.query_selector("a")
                if link:
                    match_url = link.get_attribute("href")
                    if match_url and not match_url.startswith("http"):
                        match_url = "https://www.flashscore.com" + match_url
                    break

        if not match_url:
            browser.close()
            return None

        odds_url = match_url.rstrip("/") + "/#/odds-comparison/1x2-odds/full-time"
        page.goto(odds_url, wait_until="domcontentloaded", timeout=60000)  # ✅ JAVÍTVA
        page.wait_for_timeout(4000)

        rows = page.query_selector_all("div[class*='oddsCell'], div[class*='oddsRow'], tr[class*='odd']")

        all_1, all_x, all_2 = [], [], []

        for row in rows:
            cells = row.query_selector_all("span[class*='oddsCell__odd'], div[class*='oddsCell__odd']")
            if len(cells) >= 3:
                try:
                    v1 = float(cells[0].inner_text().strip())
                    vx = float(cells[1].inner_text().strip())
                    v2 = float(cells[2].inner_text().strip())
                    if 1.01 <= v1 <= 25:
                        all_1.append(v1)
                        all_x.append(vx)
                        all_2.append(v2)
                except Exception:
                    continue

        browser.close()

        if all_1:
            return {
                "source": "flashscore",
                "odds_1": round(sum(all_1) / len(all_1), 2),
                "odds_x": round(sum(all_x) / len(all_x), 2),
                "odds_2": round(sum(all_2) / len(all_2), 2),
                "odds_1_best": max(all_1),
                "odds_x_best": max(all_x),
                "odds_2_best": max(all_2),
            }

except Exception as e:
    log.warning(f"[Flashscore] Hiba: {e}")

return None
```

# —————————————————————————

# FŐ FÜGGVÉNY — összesített odds gyűjtés

# —————————————————————————

def get_best_odds_playwright(home_team: str, away_team: str) -> dict:
“””
Összesített odds gyűjtés Playwright-tal.
“””
import statistics

```
results = {}
sources_tried = []

# 1. OddsPortal
try:
    op = scrape_oddsportal(home_team, away_team)
    if op:
        results["oddsportal"] = op
        sources_tried.append("oddsportal")
except Exception as e:
    log.debug(f"OddsPortal skip: {e}")

# 2. Flashscore
try:
    fs = scrape_flashscore(home_team, away_team)
    if fs:
        results["flashscore"] = fs
        sources_tried.append("flashscore")
except Exception as e:
    log.debug(f"Flashscore skip: {e}")

# 3. BettingExpert (csak ha a többi nem adott eredményt)
if not results:
    try:
        be = scrape_bettingexpert(home_team, away_team)
        if be:
            results["bettingexpert"] = be
            sources_tried.append("bettingexpert")
    except Exception as e:
        log.debug(f"BettingExpert skip: {e}")

# Összesítés
all_1, all_x, all_2 = [], [], []

for src, data in results.items():
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
    "odds_1_best": max(all_1),
    "odds_x_best": max(all_x) if all_x else None,
    "odds_2_best": max(all_2),
    "implied_prob_1": round(1 / avg_1, 3) if avg_1 else None,
    "implied_prob_x": round(1 / avg_x, 3) if avg_x else None,
    "implied_prob_2": round(1 / avg_2, 3) if avg_2 else None,
    "odds_spread_1": spread_1,
    "odds_spread_2": spread_2,
    "market_uncertainty": "magas" if max(spread_1, spread_2) > 0.15 else "alacsony",
    "raw": results,
}
```
