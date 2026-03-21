#!/usr/bin/env python3
"""Try to find Tippmix.hu hidden API endpoints."""
import requests
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tippmix.hu/"
}

# Common API endpoints to try
endpoints = [
    "https://www.tippmix.hu/api/events",
    "https://www.tippmix.hu/api/sports/football",
    "https://www.tippmix.hu/rest/events",
    "https://www.tippmix.hu/rest/sport/1",  # 1 = football
    "https://bet.szerencsejatek.hu/api/events",
    "https://bet.szerencsejatek.hu/rest/sport",
]

print("Testing Tippmix API endpoints...\n")

for url in endpoints:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"[{r.status_code}] {url}")
        
        if r.status_code == 200:
            try:
                data = r.json()
                print(f"  [OK] JSON response! Keys: {list(data.keys())[:5]}")
                
                # Save first successful response
                with open("tippmix_api_sample.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  [SAVED] tippmix_api_sample.json")
                break
            except:
                print(f"  [HTML] response (length: {len(r.text)})")
        elif r.status_code == 404:
            print(f"  [404] Not found")
        elif r.status_code == 403:
            print(f"  [403] Forbidden")
            
    except Exception as e:
        print(f"  [ERR] {repr(e)}")
    
    print()
