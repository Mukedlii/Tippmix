#!/usr/bin/env python3
"""
Odds Enrichment for Marketing Format

Adds best bookmaker odds to tips before sending to Telegram.
Lightweight - only enriches VIP tips (not all matches).
"""

from typing import List, Dict
from bot.providers.odds_comparison import find_best_odds


def enrich_vip_tips_with_best_odds(tips: List[Dict], max_enrichments: int = 6) -> List[Dict]:
    """
    Add best odds info to VIP tips (top N only to save time)
    
    Adds to each tip:
    - best_bookie: str
    - best_odds: float
    - odds_comparison_summary: str (short, 1-line)
    
    Args:
        tips: List of tip dicts
        max_enrichments: Max tips to enrich (rate limiting)
    
    Returns:
        Modified tips list
    """
    
    enriched_count = 0
    
    for tip in tips:
        if enriched_count >= max_enrichments:
            break
        
        home = tip.get('home_team')
        away = tip.get('away_team')
        selection = tip.get('tip') or tip.get('selection')
        
        if not (home and away and selection):
            continue
        
        # Only enrich if highlighted or high confidence
        is_highlighted = tip.get('is_highlighted', False)
        confidence = tip.get('confidence', 0)
        
        if not is_highlighted and confidence < 3.5:
            continue  # Skip low-confidence tips
        
        print(f"  Enriching odds for {home} vs {away}...")
        
        try:
            comparison = find_best_odds(home, away, selection)
            
            if comparison and comparison.get('best_odds'):
                tip['best_bookie'] = comparison['best_bookie']
                tip['best_odds'] = comparison['best_odds']
                
                # 1-line summary
                best = comparison['best_bookie']
                odds = comparison['best_odds']
                profit_diff = comparison.get('profit_diff', 0)
                
                if profit_diff > 2:  # Only show if >2% better
                    tip['odds_comparison_summary'] = f"{best.upper()} @ {odds} (+{profit_diff:.0f}% vs worst)"
                else:
                    tip['odds_comparison_summary'] = f"{best.upper()} @ {odds}"
                
                enriched_count += 1
            
        except Exception as e:
            print(f"  Error enriching odds: {e}")
            continue
    
    print(f"Enriched {enriched_count} tips with best odds")
    
    return tips


def format_odds_for_telegram(tip: Dict) -> str:
    """
    Format odds line for Telegram (replaces default "Odds: TBA")
    
    Returns:
        "📊 Odds: Bet365 @ 2.10 (+8% vs worst)"
        or
        "📊 Odds: TBA"
    """
    
    if 'best_odds' in tip and 'best_bookie' in tip:
        bookie = tip['best_bookie'].upper()
        odds = tip['best_odds']
        
        if 'odds_comparison_summary' in tip:
            return f"📊 Odds: {tip['odds_comparison_summary']}"
        else:
            return f"📊 Odds: {bookie} @ {odds}"
    
    # Fallback
    odds_estimate = tip.get('odds_estimate') or tip.get('odds_pick')
    if odds_estimate:
        return f"📊 Odds: {odds_estimate:.2f}"
    
    return "📊 Odds: TBA"
