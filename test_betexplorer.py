#!/usr/bin/env python3
"""Test BetExplorer scraping for odds."""
import requests
from bs4 import BeautifulSoup
import re

def scrape_betexplorer():
    url = "https://www.betexplorer.com/next/football/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    r = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Debug: print structure
    print("=== BETEXPLORER STRUCTURE ===")
    print(f"Total links: {len(soup.find_all('a'))}")
    print(f"Total tables: {len(soup.find_all('table'))}")
    
    # Find match rows
    matches = soup.find_all('tr')
    print(f"\nTotal rows: {len(matches)}")
    
    for i, match in enumerate(matches[:5]):
        text = match.get_text(strip=True)
        if len(text) > 10:
            print(f"\nRow {i}: {text[:200]}")
            
            # Look for odds
            odds_spans = match.find_all(['span', 'td'], class_=re.compile(r'odd|koef|kurs', re.I))
            if odds_spans:
                print(f"  Odds elements: {[x.get_text(strip=True) for x in odds_spans[:5]]}")

if __name__ == "__main__":
    scrape_betexplorer()
