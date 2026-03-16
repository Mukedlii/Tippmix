"""
bot/providers/web_context.py

Ingyenes web kontextus gyűjtő a Tippmix bothoz.
API key nélkül, scraping alapon.

Mit gyűjt:
  1. BBC Sport / ESPN - meccs előzetes (injury news, form)
  2. Understat.com - xG adatok (ingyenes, scrapelhető)
  3. SofaScore nyilvános oldal - head-to-head, form
  4. FBref.com - részletes stat (ingyenes)
  5. Google News - meccs specifikus hírek

Hogyan használja a bot:
  - A main.py meghívja build_match_context(home, away, league)
  - Az eredmény bekerül a GPT promptba extra kontextusként
  - Jobb döntések, pontosabb reasoning
"""

from __future__ import annotations

import re
import time
import random
import logging
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

def _get(url: str, timeout: int = 12) -> Optional[str]:
    """Simple HTTP GET with polite delay."""
    try:
        time.sleep(random.uniform(0.8, 1.5))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.debug(f"HTTP {r.status_code} for {url}")
    except Exception as e:
        log.debug(f"Fetch failed {url}: {e}")
    return None


# ──────────────────────────────────────────────
# 1. UNDERSTAT - xG adatok (Premier League, La Liga, Bundesliga, Serie A, Ligue 1)
# ──────────────────────────────────────────────

UNDERSTAT_LEAGUE_MAP = {
    "premier league": "EPL",
    "la liga": "La_liga",
    "bundesliga": "Bundesliga",
    "serie a": "Serie_A",
    "ligue 1": "Ligue_1",
    "rfpl": "RFPL",
}

def get_understat_team_xg(team_name: str, league_name: str) -> Optional[dict]:
    """
    Lekéri egy csapat utolsó 5 meccsének xG adatait az Understat-ról.
    Visszaad: {team, last5_xg_for, last5_xg_against, form}
    """
    league_key = None
    for k, v in UNDERSTAT_LEAGUE_MAP.items():
        if k in (league_name or "").lower():
            league_key = v
            break

    if not league_key:
        return None

    url = f"https://understat.com/league/{league_key}"
    html = _get(url)
    if not html:
        return None

    try:
        # Understat JSON-t injektál a page-be
        matches = re.findall(r"teamsData\s*=\s*JSON\.parse\('(.+?)'\)", html)
        if not matches:
            return None

        import json
        raw = matches[0].encode().decode("unicode_escape")
        data = json.loads(raw)

        # Keresés csapatnévre (case-insensitive, részleges egyezés)
        team_data = None
        for _team_id, team_info in data.items():
            if team_name.lower() in team_info.get("title", "").lower():
                team_data = team_info
                break

        if not team_data:
            return None

        history = team_data.get("history", [])[-5:]  # utolsó 5 meccs
        if not history:
            return None

        xg_for = sum(float(m.get("xG", 0)) for m in history) / len(history)
        xg_against = sum(float(m.get("xGA", 0)) for m in history) / len(history)
        pts = sum(int(m.get("pts", 0)) for m in history)

        return {
            "team": team_name,
            "last5_xg_for": round(xg_for, 2),
            "last5_xg_against": round(xg_against, 2),
            "last5_pts": pts,
            "form_label": "Jó forma" if pts >= 10 else ("Közepes" if pts >= 6 else "Gyenge forma"),
        }
    except Exception as e:
        log.debug(f"Understat parse error: {e}")
        return None


# ──────────────────────────────────────────────
# 2. FBREF - Head to Head + recent form
# ──────────────────────────────────────────────

def search_fbref_team(team_name: str) -> Optional[str]:
    """FBref csapat URL keresése."""
    url = f"https://fbref.com/search/search.fcgi?search={requests.utils.quote(team_name)}"
    html = _get(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    # Az első squad link
    link = soup.select_one("div.search-item-name a[href*='/squads/']")
    if link:
        return "https://fbref.com" + link["href"]
    return None


def get_fbref_recent_form(team_name: str) -> Optional[dict]:
    """
    FBref-ről lekéri az utolsó 5 meccs eredményét.
    """
    team_url = search_fbref_team(team_name)
    if not team_url:
        return None

    html = _get(team_url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        # Scores & Fixtures tábla
        table = soup.select_one("table#matchlogs_for")
        if not table:
            return None

        rows = table.select("tbody tr:not(.spacer):not(.thead)")[-5:]
        results = []
        for row in rows:
            result_cell = row.select_one("td[data-stat='result']")
            gf_cell = row.select_one("td[data-stat='goals_for']")
            ga_cell = row.select_one("td[data-stat='goals_against']")
            if result_cell:
                results.append({
                    "result": result_cell.get_text(strip=True),
                    "gf": gf_cell.get_text(strip=True) if gf_cell else "?",
                    "ga": ga_cell.get_text(strip=True) if ga_cell else "?",
                })

        wins = sum(1 for r in results if r["result"] == "W")
        draws = sum(1 for r in results if r["result"] == "D")
        losses = sum(1 for r in results if r["result"] == "L")

        return {
            "team": team_name,
            "last5_results": [r["result"] for r in results],
            "last5_record": f"{wins}W-{draws}D-{losses}L",
            "last5_scores": [f"{r['gf']}-{r['ga']}" for r in results],
        }
    except Exception as e:
        log.debug(f"FBref parse error: {e}")
        return None


# ──────────────────────────────────────────────
# 3. GOOGLE NEWS - Meccs specifikus hírek
# ──────────────────────────────────────────────

def get_match_news(home_team: str, away_team: str, max_results: int = 5) -> list[dict]:
    """
    Google News keresés a meccsről (sérülések, forma, csapat hírek).
    Ingyenes, scrapelhető.
    """
    query = f"{home_team} vs {away_team} injury team news prediction"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en&gl=US&ceid=US:en"

    html = _get(url)
    if not html:
        return []

    try:
        soup = BeautifulSoup(html, "xml")
        items = soup.find_all("item")[:max_results]
        news = []
        for item in items:
            title = item.find("title")
            pub_date = item.find("pubDate")
            source = item.find("source")
            news.append({
                "title": title.get_text(strip=True) if title else "",
                "published": pub_date.get_text(strip=True) if pub_date else "",
                "source": source.get_text(strip=True) if source else "",
            })
        return news
    except Exception as e:
        log.debug(f"News parse error: {e}")
        return []


# ──────────────────────────────────────────────
# 4. TRANSFERMARKT - Sérülés lista (ingyenes)
# ──────────────────────────────────────────────

def get_transfermarkt_injuries(team_name: str) -> Optional[list]:
    """
    Sérült/hiányzó játékosok a Transfermarkt-ról.
    """
    search_url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={requests.utils.quote(team_name)}&Verein_page=0"
    html = _get(search_url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        # Első csapat találat
        team_link = soup.select_one("table.items td.hauptlink a[href*='/startseite/verein/']")
        if not team_link:
            return None

        team_url = "https://www.transfermarkt.com" + team_link["href"]
        # Sérülés oldal
        injury_url = team_url.replace("/startseite/", "/sperren-und-verletzungen/")

        injury_html = _get(injury_url)
        if not injury_html:
            return None

        injury_soup = BeautifulSoup(injury_html, "html.parser")
        rows = injury_soup.select("table.items tbody tr")

        injured = []
        for row in rows[:8]:  # max 8
            name_cell = row.select_one("td.hauptlink a")
            reason_cell = row.select_one("td:nth-child(4)")
            until_cell = row.select_one("td:nth-child(6)")
            if name_cell:
                injured.append({
                    "player": name_cell.get_text(strip=True),
                    "reason": reason_cell.get_text(strip=True) if reason_cell else "?",
                    "until": until_cell.get_text(strip=True) if until_cell else "?",
                })
        return injured if injured else None
    except Exception as e:
        log.debug(f"Transfermarkt parse error: {e}")
        return None


# ──────────────────────────────────────────────
# 5. FÓ FÜGGVÉNY - Összesített kontextus
# ──────────────────────────────────────────────

def build_match_context(
    home_team: str,
    away_team: str,
    league_name: str = "",
    fetch_injuries: bool = True,
    fetch_news: bool = True,
    fetch_xg: bool = True,
    fetch_form: bool = False,  # FBref lassabb, alapból ki
) -> dict:
    """
    Összegyűjti az összes elérhető ingyenes kontextust egy meccshez.

    Visszaad egy dict-et ami bekerül a GPT promptba.
    """
    ctx: dict = {
        "home_team": home_team,
        "away_team": away_team,
        "league": league_name,
    }

    log.info(f"[WebContext] Gyűjtés: {home_team} vs {away_team}")

    # xG adatok (Understat - csak top 5 liga)
    if fetch_xg:
        home_xg = get_understat_team_xg(home_team, league_name)
        away_xg = get_understat_team_xg(away_team, league_name)
        if home_xg:
            ctx["home_xg"] = home_xg
            log.info(f"[WebContext] Home xG: {home_xg}")
        if away_xg:
            ctx["away_xg"] = away_xg
            log.info(f"[WebContext] Away xG: {away_xg}")

    # Hírek
    if fetch_news:
        news = get_match_news(home_team, away_team)
        if news:
            ctx["news"] = news
            log.info(f"[WebContext] {len(news)} hír találva")

    # Sérülések (Transfermarkt - lassabb, opcionális)
    if fetch_injuries:
        home_inj = get_transfermarkt_injuries(home_team)
        away_inj = get_transfermarkt_injuries(away_team)
        if home_inj:
            ctx["home_injuries"] = home_inj
            log.info(f"[WebContext] Home sérülések: {len(home_inj)}")
        if away_inj:
            ctx["away_injuries"] = away_inj
            log.info(f"[WebContext] Away sérülések: {len(away_inj)}")

    # FBref forma (lassabb)
    if fetch_form:
        home_form = get_fbref_recent_form(home_team)
        away_form = get_fbref_recent_form(away_team)
        if home_form:
            ctx["home_form"] = home_form
        if away_form:
            ctx["away_form"] = away_form

    return ctx


def format_context_for_prompt(ctx: dict) -> str:
    """
    A context dict-et olvasható szöveggé alakítja a GPT prompt számára.
    """
    if not ctx:
        return ""

    lines = ["=== EXTRA KONTEXTUS (web adatok) ==="]

    home = ctx.get("home_team", "Hazai")
    away = ctx.get("away_team", "Vendég")

    # xG
    home_xg = ctx.get("home_xg")
    away_xg = ctx.get("away_xg")
    if home_xg or away_xg:
        lines.append("\n📊 xG adatok (utolsó 5 meccs átlag):")
        if home_xg:
            lines.append(
                f"  {home}: xG FOR={home_xg['last5_xg_for']} | xG AGAINST={home_xg['last5_xg_against']} | Forma: {home_xg['form_label']}"
            )
        if away_xg:
            lines.append(
                f"  {away}: xG FOR={away_xg['last5_xg_for']} | xG AGAINST={away_xg['last5_xg_against']} | Forma: {away_xg['form_label']}"
            )

    # Forma
    home_form = ctx.get("home_form")
    away_form = ctx.get("away_form")
    if home_form or away_form:
        lines.append("\n📈 Legutóbbi forma:")
        if home_form:
            lines.append(f"  {home}: {home_form['last5_record']} ({' '.join(home_form['last5_results'])})")
        if away_form:
            lines.append(f"  {away}: {away_form['last5_record']} ({' '.join(away_form['last5_results'])})")

    # Sérülések
    home_inj = ctx.get("home_injuries")
    away_inj = ctx.get("away_injuries")
    if home_inj:
        lines.append(f"\n🚑 {home} sérültek/hiányzók:")
        for p in home_inj[:5]:
            lines.append(f"  - {p['player']} ({p['reason']}, vissza: {p['until']})")
    if away_inj:
        lines.append(f"\n🚑 {away} sérültek/hiányzók:")
        for p in away_inj[:5]:
            lines.append(f"  - {p['player']} ({p['reason']}, vissza: {p['until']})")

    # Hírek
    news = ctx.get("news", [])
    if news:
        lines.append("\n📰 Meccs előzetes hírek:")
        for n in news[:3]:
            lines.append(f"  - {n['title']} [{n['source']}]")

    lines.append("=== KONTEXTUS VÉGE ===")
    return "\n".join(lines)
