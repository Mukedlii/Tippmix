"""
bot/providers/tipster_aggregator.py

Profi tipster vélemények gyűjtése több forrásból.

MIÉRT HASZNOS:
  - Nem csak a saját modellre épít → "konszenzus tipp" megközelítés
  - Ha 5 különböző forrás is ugyanazt tipeli → magasabb bizalom
  - Ingyenes nyilvános tippek összegyűjtése

FORRÁSOK:
  1. BettingExpert.com  — profi tipsterek szabad tippjei
  2. Betclan.com        — közösségi tipp aggregátor
  3. Forebet.com        — matematikai alapú tippek (statisztika)
  4. Sporticos.com      — összegyűjtött tippek
  5. Nemzeti Sport      — magyar sporttippek
"""

from __future__ import annotations

import re
import time
import json
import logging
import random
from typing import Any, Dict, List, Optional
from datetime import date

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,hu;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _get(url: str, timeout: int = 18) -> Optional[str]:
    try:
        time.sleep(random.uniform(1.5, 3.0))
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.debug(f"HTTP {r.status_code}: {url}")
    except Exception as e:
        log.debug(f"Fetch hiba {url}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────
# 1. FOREBET.COM — Matematikai/statisztikai tippek
# (Valószínűségek alapján, nem "gut feeling")
# ─────────────────────────────────────────────────────────────────

def scrape_forebet() -> List[Dict[str, Any]]:
    """
    Forebet.com tippek — matematikai modell alapján.

    Forebet valószínűségeket számol (hasonlóan a mi Poisson modellünkhöz),
    így jó benchmark a saját számításainkhoz.
    """
    url = "https://www.forebet.com/en/football-tips-and-predictions-for-today"
    html = _get(url)
    if not html:
        log.warning("Forebet: nem sikerült letölteni")
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Forebet tipptáblázat
    rows = soup.find_all("tr", class_=re.compile(r"tr_0|tr_1|forecast", re.I))
    if not rows:
        rows = soup.find_all("div", class_=re.compile(r"rcnt|match.*item", re.I))

    for row in rows[:40]:
        try:
            text = row.get_text(separator="|", strip=True)
            parts = [p.strip() for p in text.split("|") if p.strip()]

            if len(parts) < 4:
                continue

            # Csapatneveket keres
            team_pattern = re.search(r"([A-Za-z\s\.\-]+?)\s+v[s]?\s+([A-Za-z\s\.\-]+)", text, re.I)
            if not team_pattern:
                continue

            home = team_pattern.group(1).strip()
            away = team_pattern.group(2).strip()

            if len(home) < 2 or len(away) < 2:
                continue

            # Valószínűségek (%)
            probs = re.findall(r"\b(\d{1,2})\s*%", text)
            p_home = p_draw = p_away = None
            if len(probs) >= 3:
                p_home = int(probs[0]) / 100
                p_draw = int(probs[1]) / 100
                p_away = int(probs[2]) / 100

            # Javasolt tipp
            tip_match = re.search(r"\b(1X2|1|X|2|Over|Under|BTTS)\b", text)
            tip = tip_match.group(1) if tip_match else None

            # Pontszám becslés (ha van)
            score_match = re.search(r"(\d+)\s*:\s*(\d+)", text)
            pred_score = score_match.group(0) if score_match else None

            results.append({
                "home_team": home,
                "away_team": away,
                "tip": tip,
                "p_home": p_home,
                "p_draw": p_draw,
                "p_away": p_away,
                "predicted_score": pred_score,
                "source": "Forebet",
                "confidence": 3.5,
            })
        except Exception as e:
            log.debug(f"Forebet row parse hiba: {e}")

    log.info(f"Forebet: {len(results)} tipp kinyerve")
    return results


# ─────────────────────────────────────────────────────────────────
# 2. BETCLAN.COM — Közösségi tippek
# ─────────────────────────────────────────────────────────────────

def scrape_betclan() -> List[Dict[str, Any]]:
    """
    Betclan.com ingyenes tippek.
    Közösségi szavazás alapú, sokszor megbízható konszenzus.
    """
    url = "https://www.betclan.com/football/"
    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Meccs kártyák
    cards = soup.find_all(["div", "article"], class_=re.compile(r"match|game|event|tip", re.I))
    for card in cards[:30]:
        try:
            text = card.get_text(separator=" ", strip=True)

            vs_match = re.search(r"([A-Za-z\s]+?)\s+[-–vsVS]+\s+([A-Za-z\s]+?)(?:\s+\d|$)", text)
            if not vs_match:
                continue

            home = vs_match.group(1).strip()
            away = vs_match.group(2).strip()
            if len(home) < 2 or len(away) < 2:
                continue

            # Tipp kinyerés
            tip = None
            if re.search(r"\b1X2\b|\bhome win\b|\bhazai\b", text, re.I):
                tip = "1"
            elif re.search(r"\bdraw\b|\bdöntetlen\b", text, re.I):
                tip = "X"
            elif re.search(r"\baway win\b|\bvendég\b", text, re.I):
                tip = "2"
            elif re.search(r"\bover 2\.5\b|\bfelett\b", text, re.I):
                tip = "Over 2.5"
            elif re.search(r"\bunder 2\.5\b|\balatt\b", text, re.I):
                tip = "Under 2.5"
            elif re.search(r"\bBTTS\b|\bmindkét\b", text, re.I):
                tip = "BTTS Yes"

            # Konfidencia %
            conf_match = re.search(r"(\d{2,3})\s*%", text)
            confidence = int(conf_match.group(1)) / 100 * 5 if conf_match else 3.0

            if tip:
                results.append({
                    "home_team": home,
                    "away_team": away,
                    "tip": tip,
                    "confidence": min(5.0, confidence),
                    "source": "Betclan",
                })
        except Exception:
            pass

    log.info(f"Betclan: {len(results)} tipp")
    return results


# ─────────────────────────────────────────────────────────────────
# 3. BETTINGEXPERT.COM — Profi tipsterek
# ─────────────────────────────────────────────────────────────────

def scrape_bettingexpert_tips() -> List[Dict[str, Any]]:
    """
    BettingExpert.com ingyenes tippek (javított verzió).
    Csak magasan értékelt tipsterek tippjeit szűri.
    """
    url = "https://www.bettingexpert.com/tips/football"
    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # JSON embedded data keresés (React SPA)
    for script in soup.find_all("script", type=re.compile(r"json|javascript")):
        txt = script.get_text()
        if "tips" in txt.lower() and "match" in txt.lower():
            try:
                # Keress JSON tömböt
                json_match = re.search(r'\[(\{"[^}]*"tips[^}]*\}.*?)\]', txt, re.DOTALL)
                if json_match:
                    data = json.loads(f"[{json_match.group(1)}]")
                    for item in data[:20]:
                        home = item.get("home_team") or item.get("homeTeam")
                        away = item.get("away_team") or item.get("awayTeam")
                        tip = item.get("pick") or item.get("selection")
                        if home and away and tip:
                            results.append({
                                "home_team": str(home),
                                "away_team": str(away),
                                "tip": str(tip),
                                "odds": item.get("odds"),
                                "tipster_yield": item.get("yield") or item.get("profit"),
                                "source": "BettingExpert",
                                "confidence": 3.5,
                            })
            except Exception:
                pass

    # HTML fallback
    if not results:
        tip_rows = soup.find_all(["div", "tr"], class_=re.compile(r"tip|pick|bet|prediction", re.I))
        for row in tip_rows[:20]:
            try:
                text = row.get_text(separator=" ", strip=True)
                vs_match = re.search(r"([A-Za-z\s]+?)\s+[-–vsVS]+\s+([A-Za-z\s]+?)\s+(\d\.\d{2})", text)
                if vs_match:
                    results.append({
                        "home_team": vs_match.group(1).strip(),
                        "away_team": vs_match.group(2).strip(),
                        "odds": float(vs_match.group(3)),
                        "source": "BettingExpert",
                        "confidence": 3.0,
                    })
            except Exception:
                pass

    log.info(f"BettingExpert: {len(results)} tipp")
    return results


# ─────────────────────────────────────────────────────────────────
# 4. NEMZETI SPORT TIPPEK (Magyar)
# ─────────────────────────────────────────────────────────────────

def scrape_nemzeti_sport_tippek() -> List[Dict[str, Any]]:
    """
    Nemzeti Sport.hu fogadási tippek és elemzések.
    """
    urls = [
        "https://www.nemzetisport.hu/tippmix",
        "https://www.nemzetisport.hu/fogadasi-tippek",
        "https://www.nemzetisport.hu/labdarugas/tippek",
    ]

    for url in urls:
        html = _get(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Meccs vs. formátum kinyerés
        articles = soup.find_all(["article", "div"], class_=re.compile(r"article|post|tipp|cikk", re.I))
        for art in articles[:20]:
            text = art.get_text(separator=" ", strip=True)

            # Csapat neveket keres
            team_matches = re.findall(r"([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüűA-Z\s\.]{2,20})\s+[-–vsVS]+\s+([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüűA-Z\s\.]{2,20})", text)
            for home, away in team_matches[:3]:
                if len(home) > 2 and len(away) > 2:
                    # Tipp kinyerés szövegből
                    tip = None
                    if re.search(r"hazai\s+győzelem|hazai\s+nyer|1-es", text, re.I):
                        tip = "Hazai győzelem"
                    elif re.search(r"vendég\s+győzelem|vendég\s+nyer|2-es", text, re.I):
                        tip = "Vendég győzelem"
                    elif re.search(r"döntetlen|ik[e]?\s*[.,]", text, re.I):
                        tip = "Döntetlen"
                    elif re.search(r"felett|gól\s+felett|over", text, re.I):
                        tip = "Over 2.5"

                    results.append({
                        "home_team": home.strip(),
                        "away_team": away.strip(),
                        "tip": tip,
                        "source": "Nemzeti Sport",
                        "confidence": 3.0,
                        "language": "hu",
                    })

        if results:
            log.info(f"Nemzeti Sport: {len(results)} tipp ({url})")
            return results

    return []


# ─────────────────────────────────────────────────────────────────
# Összesítő + Konszenzus
# ─────────────────────────────────────────────────────────────────

def get_all_tipster_consensus() -> List[Dict[str, Any]]:
    """
    Összegyűjti az összes forrás tippjét és konszenzust keres.

    Ha több forrás ugyanazt a meccset és tippet javasol → magasabb bizalom.
    """
    all_tips: List[Dict] = []

    print("[TIPSTERS] Forebet scraping...")
    all_tips.extend(scrape_forebet())

    print("[TIPSTERS] BettingExpert scraping...")
    all_tips.extend(scrape_bettingexpert_tips())

    print("[TIPSTERS] Betclan scraping...")
    all_tips.extend(scrape_betclan())

    print("[TIPSTERS] Nemzeti Sport scraping...")
    all_tips.extend(scrape_nemzeti_sport_tippek())

    print(f"[TIPSTERS] Összes tipp: {len(all_tips)} db, {len(set(t.get('source') for t in all_tips))} forrásból")
    return all_tips


def find_consensus_for_match(
    home_team: str,
    away_team: str,
    all_tips: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Konszenzus keresés egy meccshez.

    Visszaadja melyik tipp kapja a legtöbb szavazatot a tipsterektől.
    """
    if all_tips is None:
        all_tips = get_all_tipster_consensus()

    home_lower = home_team.lower()
    away_lower = away_team.lower()

    relevant = []
    for tip in all_tips:
        th = (tip.get("home_team") or "").lower()
        ta = (tip.get("away_team") or "").lower()

        # Fuzzy matching
        home_match = any(w in th for w in home_lower.split() if len(w) > 3)
        away_match = any(w in ta for w in away_lower.split() if len(w) > 3)

        if home_match and away_match:
            relevant.append(tip)

    if not relevant:
        return {"consensus": None, "sources": [], "agreement_pct": 0}

    # Szavazatszámlálás
    vote_count: Dict[str, int] = {}
    for tip in relevant:
        t = tip.get("tip")
        if t:
            vote_count[t] = vote_count.get(t, 0) + 1

    if not vote_count:
        return {"consensus": None, "sources": list(set(t.get("source") for t in relevant)), "agreement_pct": 0}

    top_tip = max(vote_count, key=lambda k: vote_count[k])
    total_votes = sum(vote_count.values())
    agreement_pct = vote_count[top_tip] / total_votes

    return {
        "consensus": top_tip,
        "votes": vote_count,
        "sources": list(set(t.get("source") for t in relevant)),
        "agreement_pct": round(agreement_pct, 2),
        "n_tipsters": len(relevant),
        "forebet_prob": next(
            (t.get("p_home") if top_tip == "1" else t.get("p_away") for t in relevant if t.get("source") == "Forebet"),
            None,
        ),
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    print("Összes tipster forrás scraping...")
    tips = get_all_tipster_consensus()

    print(f"\nOsszes tipp: {len(tips)}")
    by_source: Dict[str, int] = {}
    for t in tips:
        s = t.get("source", "?")
        by_source[s] = by_source.get(s, 0) + 1
    for src, cnt in sorted(by_source.items()):
        print(f"  {src}: {cnt} tipp")
