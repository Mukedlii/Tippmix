#!/usr/bin/env python3
"""
Manual bet tracking stats
Reads manual_bets_*.json files and displays summary
"""
import json
import glob
import os
from datetime import datetime

def load_manual_bets():
    """Load all manual bet tracking files"""
    files = glob.glob("data/manual_bets_*.json")
    all_bets = []
    
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                all_bets.append(data)
        except Exception as e:
            print(f"Error loading {f}: {e}")
    
    return all_bets

def print_summary(all_bets):
    """Print aggregate stats"""
    if not all_bets:
        print("No manual bets tracked yet.")
        return
    
    total_profit = sum(b['summary']['net_profit'] for b in all_bets)
    total_stake = sum(b['summary']['total_stake'] for b in all_bets)
    total_wins = sum(b['summary']['wins'] for b in all_bets)
    total_bets = sum(b['summary']['total_bets'] for b in all_bets)
    
    win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0
    roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
    
    print("\n" + "="*50)
    print("TIPPMIX MANUAL TRACKING OSSZESITO")
    print("="*50)
    print(f"Napok szama: {len(all_bets)}")
    print(f"Osszes tipp: {total_bets}")
    print(f"Nyero: {total_wins}")
    print(f"Vesztes: {total_bets - total_wins}")
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Osszes tet: {total_stake:,} HUF")
    print(f"Osszes profit: {total_profit:+,} HUF")
    print(f"ROI: {roi:+.1f}%")
    print("="*50)
    
    # Daily breakdown
    print("\nNAPI BONTAS:")
    print("-"*50)
    for bet_day in sorted(all_bets, key=lambda x: x['date']):
        s = bet_day['summary']
        print(f"{bet_day['date']}: {s['wins']}/{s['total_bets']} win | "
              f"{s['net_profit']:+,} HUF | ROI: {s['roi']*100:+.1f}%")
    print()

if __name__ == "__main__":
    bets = load_manual_bets()
    print_summary(bets)
