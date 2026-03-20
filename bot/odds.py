from typing import Any, Dict, Optional
import requests

from bot.api_keys import get_api_sports_key, resolve_sports_provider

_API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

# egyszerĹ± futĂˇs-cache
_ODDS_CACHE: Dict[int, Dict[str, float]] = {}


def _headers() -> Dict[str, str]:
    return {"x-apisports-key": get_api_sports_key()}


def fetch_api_football_1x2_odds(fixture_id: int, home_team: str = "", away_team: str = "") -> Dict[str, float]:
    """
    API-FOOTBALL odds lekĂ©rĂ©s (1X2 / Match Winner).
    
    Ha API-FOOTBALL nem ad eredmĂ©nyt, fallback: Tippmix/Nemzeti Sport scraping.

    Visszaad: {"1": 2.02, "X": 3.80, "2": 3.15} vagy {} ha nincs / nem talĂˇlhatĂł.
    """
    if resolve_sports_provider() != "api-sports":
        # Non-API-Sports provider: use scraper
        return _scraper_fallback(home_team, away_team)

    try:
        fid = int(fixture_id)
    except Exception:
        return _scraper_fallback(home_team, away_team)

    if fid in _ODDS_CACHE:
        return _ODDS_CACHE[fid]

    try:
        url = f"{_API_FOOTBALL_BASE}/odds"
        r = requests.get(url, headers=_headers(), params={"fixture": fid}, timeout=25)
        if r.status_code != 200:
            # Fallback to scraper
            print(f"API-Football returned {r.status_code}, trying scraper...")
            return _scraper_fallback(home_team, away_team)

        data = r.json() or {}
        resp = data.get("response") or []
        if not resp:
            # Fallback to scraper
            print(f"API-Football returned empty response, trying scraper...")
            return _scraper_fallback(home_team, away_team)

        best: Dict[str, float] = {}

        # KeressĂĽk a "Match Winner"/"Match Result"/"1X2" jellegĹ± piacot.
        for item in resp:
            for bm in (item.get("bookmakers") or []):
                for bet in (bm.get("bets") or []):
                    name = (bet.get("name") or "").lower()
                    if ("match winner" in name) or ("match result" in name) or (name.strip() == "1x2"):
                        tmp: Dict[str, float] = {}
                        for v in (bet.get("values") or []):
                            val = (v.get("value") or "").strip()
                            odd_raw = v.get("odd")
                            try:
                                odd = float(odd_raw)
                            except Exception:
                                continue

                            # kĂĽlĂ¶nbĂ¶zĹ‘ elnevezĂ©sek
                            if val in ("Home", "1"):
                                tmp["1"] = odd
                            elif val in ("Draw", "X"):
                                tmp["X"] = odd
                            elif val in ("Away", "2"):
                                tmp["2"] = odd

                        if tmp.get("1") and tmp.get("X") and tmp.get("2"):
                            best = tmp
                            break
                if best:
                    break
            if best:
                break

        if not best:
            # Fallback to scraper
            print(f"API-Football found no 1X2 odds, trying scraper...")
            return _scraper_fallback(home_team, away_team)

        _ODDS_CACHE[fid] = best
        return best

    except Exception as e:
        print(f"API-Football error: {repr(e)}, trying scraper...")
        return _scraper_fallback(home_team, away_team)


def _scraper_fallback(home_team: str, away_team: str) -> Dict[str, float]:
    """
    Fallback: scrape Tippmix.hu or Nemzeti Sport for odds.
    """
    if not home_team or not away_team:
        return {}
    
    try:
        from bot.odds_scraper import get_odds_with_fallback
        odds = get_odds_with_fallback(home_team, away_team)
        return odds if odds else {}
    except Exception as e:
        print(f"Scraper fallback failed: {repr(e)}")
        return {}
