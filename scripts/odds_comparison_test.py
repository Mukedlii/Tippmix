#!/usr/bin/env python3
"""
Odds Comparison Test Script

Tests odds comparison for today's picks.
Run manually to check which bookmaker has best odds.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.providers.odds_comparison import find_best_odds, format_odds_comparison


def main():
    print("="*60)
    print("ODDS COMPARISON TEST")
    print("="*60)
    
    # Test cases (today's matches)
    test_matches = [
        ("AFC Bournemouth", "Manchester United", "Vendég győzelem"),
        ("RB Leipzig", "Hoffenheim", "Hazai győzelem"),
        ("Genoa", "Udinese", "Döntetlen"),
    ]
    
    for home, away, pick in test_matches:
        print(f"\n{home} vs {away}")
        print(f"Pick: {pick}")
        print("-" * 40)
        
        result = find_best_odds(home, away, pick)
        
        if result:
            print(format_odds_comparison(result, stake=1000))
        else:
            print("No odds comparison available")
        
        print()


if __name__ == "__main__":
    main()
