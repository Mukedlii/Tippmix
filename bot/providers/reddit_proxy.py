#!/usr/bin/env python3
"""
Reddit scraper with proxy/retry for GitHub Actions
Uses multiple fallback methods to avoid 403
"""
import requests
import time
from typing import Optional

# Free proxy services (rotate if one fails)
PROXY_APIS = [
    None,  # Try direct first
    # Add proxy services if needed
]

def fetch_reddit_with_retry(subreddit: str, max_retries: int = 3) -> Optional[dict]:
    """
    Fetch Reddit with retry and fallback strategies
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    
    for attempt in range(max_retries):
        try:
            # Try direct first
            resp = requests.get(url, headers=headers, timeout=20)
            
            if resp.status_code == 200:
                return resp.json()
            
            if resp.status_code == 403:
                print(f"[Reddit] 403 on attempt {attempt+1}, retrying...")
                time.sleep(5 * (attempt + 1))  # Exponential backoff
                
                # Try different User-Agent
                headers["User-Agent"] = f"Tippmix/{attempt+1}.0"
                continue
            
            print(f"[Reddit] HTTP {resp.status_code}")
            return None
            
        except Exception as e:
            print(f"[Reddit] Error attempt {attempt+1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
    
    return None
