#!/usr/bin/env python3
"""
Alternative Reddit scraper - uses old.reddit.com and different headers
Works better with GitHub Actions IPs
"""
import requests
import time
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def get_daily_picks_thread_alternative(subreddit: str = "SoccerBetting") -> Optional[str]:
    """
    Alternative method using old.reddit.com
    Often works when new.reddit.com is blocked
    """
    # Try old.reddit.com first (different IP routing)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    # Try multiple approaches
    urls = [
        f"https://old.reddit.com/r/{subreddit}/new/.json",
        f"https://www.reddit.com/r/{subreddit}/new.json",
        f"https://old.reddit.com/r/{subreddit}/new",  # HTML fallback
    ]
    
    for url in urls:
        try:
            time.sleep(2)  # Rate limiting
            resp = requests.get(url, headers=headers, timeout=20)
            
            if resp.status_code == 200:
                if '.json' in url:
                    return parse_json_response(resp.json(), subreddit)
                else:
                    return parse_html_response(resp.text, subreddit)
            
            print(f"[Reddit Alt] {url} returned {resp.status_code}")
            
        except Exception as e:
            print(f"[Reddit Alt] Error with {url}: {e}")
            continue
    
    return None


def parse_json_response(data: dict, subreddit: str) -> Optional[str]:
    """Parse JSON response from Reddit API"""
    try:
        posts = data.get('data', {}).get('children', [])
        
        now = datetime.now()
        date_formats = [
            now.strftime("%B %d"),
            now.strftime("%d %B"),
            now.strftime("%dst %B") if now.day in [1,21,31] else now.strftime("%dth %B"),
        ]
        
        for post in posts:
            post_data = post.get('data', {})
            title = post_data.get('title', '').lower()
            
            if 'daily picks' in title or 'picks thread' in title:
                if 'today' in title or any(fmt.lower() in title for fmt in date_formats):
                    permalink = post_data.get('permalink', '')
                    full_url = "https://www.reddit.com" + permalink
                    print(f"[Reddit Alt] Found thread in r/{subreddit}: {post_data.get('title')}")
                    return full_url
        
        return None
        
    except Exception as e:
        print(f"[Reddit Alt] JSON parse error: {e}")
        return None


def parse_html_response(html: str, subreddit: str) -> Optional[str]:
    """Parse HTML response as fallback"""
    try:
        soup = BeautifulSoup(html, 'lxml')
        posts = soup.find_all('div', class_='thing')
        
        for post in posts[:20]:  # Check first 20 posts
            title_elem = post.find('a', class_='title')
            if not title_elem:
                continue
            
            title = title_elem.text.lower()
            
            if 'daily picks' in title or 'picks thread' in title:
                href = title_elem.get('href', '')
                if href.startswith('/r/'):
                    full_url = "https://www.reddit.com" + href
                    print(f"[Reddit Alt] Found thread (HTML): {title_elem.text}")
                    return full_url
        
        return None
        
    except Exception as e:
        print(f"[Reddit Alt] HTML parse error: {e}")
        return None
