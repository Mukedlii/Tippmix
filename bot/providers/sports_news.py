"""
bot/providers/sports_news.py

Sport hírek scraping meccs-specifikus információkhoz.

Források (magyar + nemzetközi):
  1. Nemzeti Sport (nemzetisport.hu)
  2. Origo Sport (origo.hu/sport)
  3. Index Sport (index.hu/sport)
  4. 444 Sport (444.hu/sport)
  5. BBC Sport (bbc.com/sport/football)
  6. ESPN FC (espn.com/soccer)
  7. The Athletic
  8. Goal.com

Használat:
  news = get_match_news("Arsenal", "Liverpool", "Premier League")
  → [{"title": "Saka injury doubt", "summary": "...", "source": "BBC Sport", "url": "..."}]
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
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
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


# ──────────────────────────────────────────────
# 1. NEMZETI SPORT (nemzetisport.hu)
# ──────────────────────────────────────────────

def search_nemzeti_sport(team_name: str, league_name: str = "") -> List[Dict[str, Any]]:
    """
    Nemzeti Sport keresés meccs-specifikus hírekre.
    """
    query = f"{team_name}"
    if league_name:
        query += f" {league_name}"
    
    search_url = f"https://www.nemzetisport.hu/kereses?q={requests.utils.quote(query)}"
    html = _get(search_url)
    if not html:
        return []

    news = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article.search-result-item, div.article-item, div.news-item")[:5]

        for article in articles:
            title_el = article.select_one("h2 a, h3 a, a.title")
            summary_el = article.select_one("p.lead, p.summary, div.excerpt")
            
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = "https://www.nemzetisport.hu" + url
            
            summary = summary_el.get_text(strip=True) if summary_el else ""

            # Csak foci hírek
            if any(kw in title.lower() for kw in ["labdarúgás", "foci", "football", "premier", "liga", "bajnokság"]):
                news.append({
                    "title": title,
                    "summary": summary[:150],
                    "source": "Nemzeti Sport",
                    "url": url,
                    "published": None,
                })

    except Exception as e:
        log.debug(f"Nemzeti Sport parse error: {e}")

    return news


# ──────────────────────────────────────────────
# 2. ORIGO SPORT (origo.hu/sport)
# ──────────────────────────────────────────────

def search_origo_sport(team_name: str) -> List[Dict[str, Any]]:
    """Origo Sport keresés."""
    query = requests.utils.quote(team_name)
    search_url = f"https://www.origo.hu/kereses.html?q={query}&section=sport"
    html = _get(search_url)
    if not html:
        return []

    news = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("div.search-result-item, article.sport-article")[:3]

        for item in items:
            title_el = item.select_one("h3 a, a.title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            if url and not url.startswith("http"):
                url = "https://www.origo.hu" + url

            news.append({
                "title": title,
                "summary": "",
                "source": "Origo Sport",
                "url": url,
                "published": None,
            })

    except Exception as e:
        log.debug(f"Origo parse error: {e}")

    return news


# ──────────────────────────────────────────────
# 3. INDEX SPORT (index.hu/sport)
# ──────────────────────────────────────────────

def search_index_sport(team_name: str) -> List[Dict[str, Any]]:
    """Index Sport keresés."""
    # Index search gyakran JavaScript-dependent, best-effort
    url = f"https://index.hu/kereses/?q={requests.utils.quote(team_name)}&c=sport"
    html = _get(url)
    if not html:
        return []

    news = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article, div.cikk")[:3]

        for article in articles:
            link = article.select_one("a[href*='/sport/']")
            if not link:
                continue

            title = link.get_text(strip=True)
            url = link.get("href", "")
            if url and not url.startswith("http"):
                url = "https://index.hu" + url

            news.append({
                "title": title,
                "summary": "",
                "source": "Index Sport",
                "url": url,
                "published": None,
            })

    except Exception as e:
        log.debug(f"Index parse error: {e}")

    return news


# ──────────────────────────────────────────────
# 4. BBC SPORT (ingyenes, angol)
# ──────────────────────────────────────────────

def search_bbc_sport(team_name: str, league_name: str = "") -> List[Dict[str, Any]]:
    """
    BBC Sport keresés meccs preview, injury news, stb.
    """
    query = f"{team_name}"
    if league_name:
        query += f" {league_name}"

    search_url = f"https://www.bbc.co.uk/search?q={requests.utils.quote(query)}&filter=football"
    html = _get(search_url)
    if not html:
        return []

    news = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        results = soup.select("article, li.ssrcss-1f3bvyz-StyledItem")[:5]

        for item in results:
            link = item.select_one("a")
            if not link:
                continue

            title = link.get_text(strip=True)
            url = link.get("href", "")
            if url and not url.startswith("http"):
                url = "https://www.bbc.co.uk" + url

            # Csak foci hírek
            if "football" in url or "sport" in url:
                news.append({
                    "title": title,
                    "summary": "",
                    "source": "BBC Sport",
                    "url": url,
                    "published": None,
                })

    except Exception as e:
        log.debug(f"BBC Sport parse error: {e}")

    return news


# ──────────────────────────────────────────────
# 5. ESPN FC (nemzetközi)
# ──────────────────────────────────────────────

def search_espn_fc(team_name: str) -> List[Dict[str, Any]]:
    """ESPN FC keresés."""
    # ESPN team pages pattern
    query = team_name.lower().replace(" ", "-")
    
    # Try team page directly
    url = f"https://www.espn.com/soccer/team/_/name/{query}"
    html = _get(url)
    if not html:
        return []

    news = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("section.TeamNews article")[:3]

        for article in articles:
            link = article.select_one("a")
            title_el = article.select_one("h1, h2, h3")
            
            if not link or not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = link.get("href", "")
            if url and not url.startswith("http"):
                url = "https://www.espn.com" + url

            news.append({
                "title": title,
                "summary": "",
                "source": "ESPN FC",
                "url": url,
                "published": None,
            })

    except Exception as e:
        log.debug(f"ESPN FC parse error: {e}")

    return news


# ──────────────────────────────────────────────
# 6. GOAL.COM (nemzetközi, injury updates)
# ──────────────────────────────────────────────

def search_goal_com(team_name: str) -> List[Dict[str, Any]]:
    """Goal.com keresés (injury news, match preview)."""
    search_url = f"https://www.goal.com/en/search/{requests.utils.quote(team_name)}/news"
    html = _get(search_url)
    if not html:
        return []

    news = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("div.widget-content-item, article")[:3]

        for article in articles:
            link = article.select_one("a")
            title_el = article.select_one("h3, h4, span.widget-content-item__title")
            
            if not link or not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = link.get("href", "")
            if url and not url.startswith("http"):
                url = "https://www.goal.com" + url

            news.append({
                "title": title,
                "summary": "",
                "source": "Goal.com",
                "url": url,
                "published": None,
            })

    except Exception as e:
        log.debug(f"Goal.com parse error: {e}")

    return news


# ──────────────────────────────────────────────
# 7. FŐ FÜGGVÉNY - Multi-source news aggregáció
# ──────────────────────────────────────────────

def get_match_news(
    home_team: str,
    away_team: str,
    league_name: str = "",
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """
    Meccs-specifikus hírek gyűjtése több forrásból.

    Args:
        home_team: Hazai csapat neve
        away_team: Vendég csapat neve
        league_name: Liga neve (kontextus)
        max_results: Maximum hír darabszám

    Returns:
        List of news: [{"title": "...", "summary": "...", "source": "...", "url": "..."}]
    """
    all_news: List[Dict[str, Any]] = []

    # Párhuzamos keresés mindkét csapatra
    for team in [home_team, away_team]:
        # Magyar források
        nemzeti = search_nemzeti_sport(team, league_name)
        all_news.extend(nemzeti)
        if nemzeti:
            log.info(f"[News] Nemzeti Sport: {team} → {len(nemzeti)} hírek")

        # Nemzetközi források
        bbc = search_bbc_sport(team, league_name)
        all_news.extend(bbc)
        if bbc:
            log.info(f"[News] BBC Sport: {team} → {len(bbc)} hírek")

        goal = search_goal_com(team)
        all_news.extend(goal)
        if goal:
            log.info(f"[News] Goal.com: {team} → {len(goal)} hírek")

        # Ha még kevés hír van, próbáljuk az Origot/Indexet is
        if len(all_news) < max_results:
            origo = search_origo_sport(team)
            all_news.extend(origo)

    # Deduplikáció title alapján
    seen = set()
    unique = []
    for article in all_news:
        title_key = article["title"].lower().strip()
        if title_key not in seen:
            seen.add(title_key)
            unique.append(article)

    # Relevancia szűrés (mindkét csapat említve)
    home_lower = home_team.lower()
    away_lower = away_team.lower()

    relevant = []
    for article in unique:
        text = (article["title"] + " " + article.get("summary", "")).lower()
        # Ha mindkét csapat szerepel, vagy injury/preview keyword
        if (home_lower[:5] in text or away_lower[:5] in text) or \
           any(kw in text for kw in ["injury", "sérülés", "eltiltás", "preview", "előzetes", "összecsapás"]):
            relevant.append(article)

    return relevant[:max_results]


def format_news_for_prompt(news: List[Dict[str, Any]], home_team: str, away_team: str) -> str:
    """
    Formázott news block AI prompt-hoz.
    """
    if not news:
        return ""

    lines = [f"📰 FRISS HÍREK ({home_team} vs {away_team}):"]

    for i, article in enumerate(news[:5], 1):
        title = article["title"]
        source = article["source"]
        summary = article.get("summary", "")
        
        lines.append(f"  {i}. [{source}] {title}")
        if summary:
            lines.append(f"     → {summary}")

    lines.append("")
    lines.append("  💡 Használd ezeket kontextusként (injury news, forma, taktika)!")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 8. MATCH PREVIEW scraping (cikk szöveg teljes)
# ──────────────────────────────────────────────

def fetch_article_content(url: str) -> Optional[str]:
    """
    Teljes cikk szöveg kinyerése (ha match preview).
    Használható részletes kontextushoz.
    """
    html = _get(url)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Próbáljuk meg a cikk tartalmát
        article = soup.select_one("article, div.article-body, div.content-body, div.story-body")
        if not article:
            return None

        # Paragrafusok
        paragraphs = article.select("p")
        text = " ".join([p.get_text(strip=True) for p in paragraphs[:10]])  # első 10 bekezdés

        return text[:1000]  # max 1000 karakter

    except Exception as e:
        log.debug(f"Article content parse error: {e}")
        return None
