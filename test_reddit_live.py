#!/usr/bin/env python3
import requests
import json
from datetime import datetime

subreddits = ["SoccerBetting", "SoccerPredictions", "sportsbetting"]

for sub in subreddits:
    print(f"\n{'='*60}")
    print(f"r/{sub}")
    print('='*60)
    
    url = f"https://www.reddit.com/r/{sub}/new.json"
    headers = {"User-Agent": "Tippmix/1.0"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            print(f"ERROR: HTTP {resp.status_code}")
            continue
        
        data = resp.json()
        posts = data.get('data', {}).get('children', [])
        
        print(f"Found {len(posts)} recent posts\n")
        
        # Show first 5 posts
        for i, post in enumerate(posts[:5], 1):
            post_data = post.get('data', {})
            title = post_data.get('title', '')
            stickied = post_data.get('stickied', False)
            score = post_data.get('score', 0)
            
            sticky_mark = " [STICKIED]" if stickied else ""
            print(f"{i}. {title}{sticky_mark}")
            print(f"   Score: {score}")
            print()
    
    except Exception as e:
        print(f"ERROR: {e}")
