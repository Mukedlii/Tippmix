"""
bot/betting_exchange.py

Betting Exchange Odds Tracking (Sharp Money Detection)
- Track opening vs closing odds movement
- Detect where sharp money is going
- Calculate value bets using market odds
- Support for Betfair API and The Odds API
"""

from __future__ import annotations

import logging
import os
import requests
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


class BettingExchangeTracker:
    """Track odds movements and detect sharp money."""

    def __init__(self):
        self.odds_api_key = os.getenv("ODDS_API_KEY")
        self.betfair_app_key = os.getenv("BETFAIR_APP_KEY")
        self.use_odds_api = bool(self.odds_api_key)
        self.cache = {}
        self.cache_timeout = 3600  # 1 hour

    def get_market_odds(self, sport_key: str = "soccer_epl") -> List[Dict]:
        """
        Fetch current market odds from The Odds API.
        
        Returns list of matches with bookmaker odds:
        [{
            "id": "...",
            "sport_key": "...",
            "home_team": "...",
            "away_team": "...",
            "commence_time": "...",
            "bookmakers": [{
                "key": "betfair",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Home", "price": 2.5},
                        {"name": "Away", "price": 1.8}
                    ]
                }]
            }]
        }]
        """
        if not self.use_odds_api:
            log.warning("ODDS_API_KEY not set")
            return []

        cache_key = f"market_odds_{sport_key}"
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if time.time() - cached_time < self.cache_timeout:
                return cached_data

        try:
            url = "https://api.the-odds-api.com/v4/sports/{}/odds/".format(sport_key)
            params = {
                "apiKey": self.odds_api_key,
                "regions": "eu,uk",
                "markets": "h2h",
                "oddsFormat": "decimal",
                "bookmakers": "betfair,pinnacle,bet365",  # Sharp bookmakers
            }

            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                self.cache[cache_key] = (data, time.time())
                log.info(f"Fetched {len(data)} matches from The Odds API")
                return data
            else:
                log.warning(f"The Odds API error: {response.status_code}")
                return []

        except Exception as e:
            log.error(f"get_market_odds error: {e}")
            return []

    def calculate_sharp_movement(
        self, 
        opening_odds: Dict[str, float], 
        current_odds: Dict[str, float]
    ) -> Dict[str, Dict]:
        """
        Calculate odds movement and detect sharp money.
        
        Args:
            opening_odds: {"1": 2.5, "X": 3.2, "2": 2.8}
            current_odds: {"1": 2.2, "X": 3.4, "2": 3.1}
        
        Returns:
            {
                "1": {"movement": -12%, "sharp_money": True, "direction": "backing"},
                "X": {"movement": +6%, "sharp_money": False, "direction": "laying"},
                "2": {"movement": +11%, "sharp_money": True, "direction": "laying"},
            }
        """
        results = {}
        
        for outcome in ["1", "X", "2"]:
            if outcome not in opening_odds or outcome not in current_odds:
                continue
                
            opening = opening_odds[outcome]
            current = current_odds[outcome]
            
            if opening <= 0:
                continue
            
            # Calculate movement percentage
            movement_pct = ((current - opening) / opening) * 100
            
            # Sharp money detection:
            # - Odds dropping (negative movement) = backing (sharp money on this outcome)
            # - Odds rising (positive movement) = laying (sharp money against)
            # - Significant movement > 5% indicates sharp action
            
            is_sharp = abs(movement_pct) > 5
            direction = "backing" if movement_pct < 0 else "laying"
            
            # Reverse implied probability
            opening_prob = (1 / opening) * 100
            current_prob = (1 / current) * 100
            prob_shift = current_prob - opening_prob
            
            results[outcome] = {
                "movement_pct": round(movement_pct, 1),
                "sharp_money": is_sharp,
                "direction": direction,
                "opening_odds": opening,
                "current_odds": current,
                "prob_shift": round(prob_shift, 1),
            }
        
        return results

    def find_value_bets(
        self,
        our_probability: Dict[str, float],
        market_odds: Dict[str, float],
        min_edge: float = 5.0
    ) -> List[Dict]:
        """
        Find value bets by comparing our probability vs market odds.
        
        Args:
            our_probability: {"1": 55, "X": 25, "2": 20}  # percentages
            market_odds: {"1": 2.0, "X": 3.5, "2": 4.5}
            min_edge: minimum edge percentage to consider a value bet
        
        Returns:
            [{"outcome": "1", "edge": 10%, "our_prob": 55%, "market_prob": 50%, "odds": 2.0}]
        """
        value_bets = []
        
        for outcome, our_prob in our_probability.items():
            if outcome not in market_odds:
                continue
            
            odds = market_odds[outcome]
            market_prob = (1 / odds) * 100
            
            # Edge = our probability - market probability
            edge = our_prob - market_prob
            
            if edge >= min_edge:
                expected_value = (our_prob / 100 * odds) - 1
                
                value_bets.append({
                    "outcome": outcome,
                    "edge": round(edge, 1),
                    "our_prob": round(our_prob, 1),
                    "market_prob": round(market_prob, 1),
                    "odds": odds,
                    "expected_value": round(expected_value * 100, 1),  # EV in %
                })
        
        # Sort by edge (highest first)
        value_bets.sort(key=lambda x: x["edge"], reverse=True)
        
        return value_bets

    def get_pinnacle_closing_odds(self, match_id: str) -> Optional[Dict[str, float]]:
        """
        Get Pinnacle closing odds (industry sharpest book).
        Pinnacle closing line is considered the most efficient market.
        """
        # This would need Pinnacle API access or scraping
        # For now, using The Odds API as proxy
        
        try:
            markets = self.get_market_odds()
            
            for match in markets:
                if match.get("id") == match_id:
                    for bookmaker in match.get("bookmakers", []):
                        if bookmaker.get("key") == "pinnacle":
                            for market in bookmaker.get("markets", []):
                                if market.get("key") == "h2h":
                                    outcomes = market.get("outcomes", [])
                                    
                                    odds_dict = {}
                                    for outcome in outcomes:
                                        name = outcome.get("name", "")
                                        price = outcome.get("price", 0)
                                        
                                        if "draw" in name.lower():
                                            odds_dict["X"] = price
                                        elif match.get("home_team") in name:
                                            odds_dict["1"] = price
                                        else:
                                            odds_dict["2"] = price
                                    
                                    return odds_dict
            
            return None
            
        except Exception as e:
            log.error(f"get_pinnacle_closing_odds error: {e}")
            return None

    def analyze_match_odds(self, fixture_id: int, home: str, away: str) -> Dict:
        """
        Comprehensive odds analysis for a single match.
        
        Returns analysis including:
        - Current best odds
        - Sharp money indicators
        - Value bet suggestions
        - Pinnacle line comparison
        """
        analysis = {
            "fixture_id": fixture_id,
            "home_team": home,
            "away_team": away,
            "timestamp": datetime.now().isoformat(),
            "best_odds": {},
            "sharp_indicators": [],
            "value_suggestions": [],
        }
        
        try:
            # Fetch current market
            markets = self.get_market_odds()
            
            # Find matching fixture (would need better matching logic in production)
            match_data = None
            for match in markets:
                if home.lower() in match.get("home_team", "").lower():
                    match_data = match
                    break
            
            if not match_data:
                return analysis
            
            # Extract best odds across bookmakers
            best_odds = {"1": 0, "X": 0, "2": 0}
            all_bookmaker_odds = []
            
            for bookmaker in match_data.get("bookmakers", []):
                bookie_name = bookmaker.get("key", "")
                
                for market in bookmaker.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    
                    odds_dict = {}
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("name", "")
                        price = outcome.get("price", 0)
                        
                        if "draw" in name.lower():
                            odds_dict["X"] = price
                            best_odds["X"] = max(best_odds["X"], price)
                        elif home in name:
                            odds_dict["1"] = price
                            best_odds["1"] = max(best_odds["1"], price)
                        else:
                            odds_dict["2"] = price
                            best_odds["2"] = max(best_odds["2"], price)
                    
                    all_bookmaker_odds.append({
                        "bookmaker": bookie_name,
                        "odds": odds_dict,
                    })
            
            analysis["best_odds"] = best_odds
            
            # Detect sharp indicators
            # Check for odds discrepancies between sharp books (Pinnacle) vs soft books
            pinnacle_odds = None
            avg_soft_odds = {"1": [], "X": [], "2": []}
            
            for bookie_data in all_bookmaker_odds:
                bookie = bookie_data["bookmaker"]
                odds = bookie_data["odds"]
                
                if bookie == "pinnacle":
                    pinnacle_odds = odds
                elif bookie in ["bet365", "williamhill", "unibet"]:
                    for outcome in ["1", "X", "2"]:
                        if outcome in odds:
                            avg_soft_odds[outcome].append(odds[outcome])
            
            if pinnacle_odds:
                for outcome in ["1", "X", "2"]:
                    if outcome not in pinnacle_odds:
                        continue
                    
                    pinnacle_odd = pinnacle_odds[outcome]
                    
                    if avg_soft_odds[outcome]:
                        avg_soft = sum(avg_soft_odds[outcome]) / len(avg_soft_odds[outcome])
                        
                        # If Pinnacle odds are significantly lower than soft books,
                        # it suggests sharp money is backing this outcome
                        discrepancy = ((avg_soft - pinnacle_odd) / pinnacle_odd) * 100
                        
                        if discrepancy > 3:  # >3% discrepancy
                            analysis["sharp_indicators"].append({
                                "outcome": outcome,
                                "signal": "sharp_backing",
                                "pinnacle_odds": pinnacle_odd,
                                "soft_avg_odds": round(avg_soft, 2),
                                "discrepancy_pct": round(discrepancy, 1),
                            })
            
            return analysis
            
        except Exception as e:
            log.error(f"analyze_match_odds error: {e}")
            return analysis


def enrich_with_exchange_data(dossier: Dict) -> Dict:
    """
    Enrich match dossier with betting exchange analysis.
    Adds sharp money indicators and value bet suggestions.
    """
    if os.getenv("TIPPMIX_USE_EXCHANGE_DATA", "1") != "1":
        return dossier
    
    tracker = BettingExchangeTracker()
    
    fixture_id = dossier.get("fixture_id")
    home = dossier.get("home", "")
    away = dossier.get("away", "")
    
    if not fixture_id or not home:
        return dossier
    
    try:
        analysis = tracker.analyze_match_odds(fixture_id, home, away)
        
        if analysis.get("best_odds"):
            dossier["market_best_odds"] = analysis["best_odds"]
        
        if analysis.get("sharp_indicators"):
            dossier["sharp_signals"] = analysis["sharp_indicators"]
        
        return dossier
        
    except Exception as e:
        log.warning(f"Failed to enrich with exchange data for {fixture_id}: {e}")
        return dossier


def format_exchange_context(dossier: Dict) -> str:
    """Format exchange analysis for AI context."""
    lines = []
    
    # Best available odds
    best_odds = dossier.get("market_best_odds", {})
    if best_odds:
        lines.append(
            f"💰 Legjobb piaci odds: 1: {best_odds.get('1', 'N/A')}, "
            f"X: {best_odds.get('X', 'N/A')}, 2: {best_odds.get('2', 'N/A')}"
        )
    
    # Sharp money signals
    sharp_signals = dossier.get("sharp_signals", [])
    if sharp_signals:
        lines.append("🔍 Sharp money jelzések:")
        for signal in sharp_signals:
            outcome_name = {"1": "Hazai", "X": "Döntetlen", "2": "Vendég"}.get(signal["outcome"], signal["outcome"])
            lines.append(
                f"   → {outcome_name}: Pinnacle @{signal['pinnacle_odds']} vs "
                f"soft books átlag @{signal['soft_avg_odds']} "
                f"({signal['discrepancy_pct']:+.1f}% különbség)"
            )
    
    return "\n".join(lines) if lines else ""
