#!/usr/bin/env python3
"""
Combo Bet Test

Tests combo builder with sample picks.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.combo_builder import build_combos, format_combo_for_telegram


# Sample VIP picks (high quality)
sample_picks = [
    {
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "tip": "Hazai győzelem",
        "confidence": 4.5,
        "risk_level": "safe",
        "best_odds": 1.65,
        "league_name": "Premier League"
    },
    {
        "home_team": "Bayern Munich",
        "away_team": "Dortmund",
        "tip": "Hazai győzelem",
        "confidence": 4.0,
        "risk_level": "közepes",
        "best_odds": 1.80,
        "league_name": "Bundesliga"
    },
    {
        "home_team": "Liverpool",
        "away_team": "Everton",
        "tip": "Hazai győzelem",
        "confidence": 4.2,
        "risk_level": "safe",
        "best_odds": 1.55,
        "league_name": "Premier League"
    },
    {
        "home_team": "Real Madrid",
        "away_team": "Atletico Madrid",
        "tip": "Hazai győzelem",
        "confidence": 3.8,
        "risk_level": "moderate",
        "best_odds": 2.10,
        "league_name": "La Liga"
    },
    {
        "home_team": "PSG",
        "away_team": "Lyon",
        "tip": "Hazai győzelem",
        "confidence": 3.5,
        "risk_level": "közepes",
        "best_odds": 1.75,
        "league_name": "Ligue 1"
    },
]


def main():
    print("="*60)
    print("COMBO BET BUILDER TEST")
    print("="*60)
    print()
    
    combos = build_combos(sample_picks)
    
    if combos['safe']:
        print("SAFE COMBO (3 TIPP)")
        print("="*60)
        print(format_combo_for_telegram(combos['safe'], "SAFE", 1000))
        print()
    else:
        print("No safe combo available")
        print()
    
    if combos['risky']:
        print("RISKY COMBO (4+ TIPP)")
        print("="*60)
        print(format_combo_for_telegram(combos['risky'], "RISKY", 1000))
        print()
    else:
        print("No risky combo available")
        print()
    
    print("="*60)
    print("SUMMARY")
    print("="*60)
    
    if combos['safe']:
        from bot.combo_builder import calculate_combo_odds
        safe_odds = calculate_combo_odds(combos['safe'])
        safe_win = int(1000 * safe_odds)
        print(f"SAFE:  1000 HUF → {safe_win:,} HUF (odds: {safe_odds:.2f})")
    
    if combos['risky']:
        from bot.combo_builder import calculate_combo_odds
        risky_odds = calculate_combo_odds(combos['risky'])
        risky_win = int(1000 * risky_odds)
        print(f"RISKY: 1000 HUF → {risky_win:,} HUF (odds: {risky_odds:.2f})")
    
    print()


if __name__ == "__main__":
    main()
