#!/usr/bin/env python3
"""
News RSS aggregator for Tippmix

Monitors breaking football news from free RSS feeds
Useful for detecting lineup changes, injuries, manager changes, etc.

Free sources:
- BBC Sport Football
- Sky Sports Football
- Goal.com
- ESPN FC
"""

import feedparser
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re


RSS_FEEDS = {
    "bbc_sport": "http://feeds.bbci.co.uk/sport/football/rss.xml",
    "sky_sports": "https://www.skysports.com/rss/12040",  # Football news
    "goal": "https://www.goal.com/feeds/en/news",
    "espn": "https://www.espnfc.com/rss",
}

# Keywords to watch for (betting relevance)
IMPORTANT_KEYWORDS = [
    # Injuries
    "injury", "injured", "sidelined", "ruled out", "doubt", "fitness",
    # Lineups
    "lineup", "starting", "bench", "suspended", "ban", 
    # Form/Performance
    "sacked", "fired", "manager", "crisis", "defeat", "win streak",
    # Transfers (mid-season impact)
    "signed", "transfer", "loan", "departure",
]


def fetch_rss_feed(feed_url: str, max_age_hours: int = 24) -> List[Dict]:
    """
    Fetch and parse RSS feed
    
    Returns:
        List of news items with title, link, published, summary
    """
    try:
        feed = feedparser.parse(feed_url)
        
        if feed.bozo:  # Parse error
            print(f"RSS parse error: {feed_url}")
            return []
        
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        items = []
        
        for entry in feed.entries:
            # Parse published date
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_date = datetime(*entry.updated_parsed[:6])
            
            # Filter by age
            if pub_date and pub_date < cutoff:
                continue
            
            items.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": pub_date.isoformat() if pub_date else None,
                "summary": entry.get("summary", ""),
            })
        
        return items
        
    except Exception as e:
        print(f"Error fetching RSS {feed_url}: {e}")
        return []


def filter_important_news(items: List[Dict], keywords: Optional[List[str]] = None) -> List[Dict]:
    """
    Filter news items by important keywords
    
    Args:
        items: List of news items
        keywords: Custom keyword list (defaults to IMPORTANT_KEYWORDS)
    
    Returns:
        Filtered list with relevance score
    """
    if keywords is None:
        keywords = IMPORTANT_KEYWORDS
    
    filtered = []
    
    for item in items:
        text = (item.get("title", "") + " " + item.get("summary", "")).lower()
        
        # Count keyword matches
        matches = sum(1 for kw in keywords if kw.lower() in text)
        
        if matches > 0:
            item["relevance_score"] = matches
            item["matched_keywords"] = [kw for kw in keywords if kw.lower() in text]
            filtered.append(item)
    
    # Sort by relevance
    filtered.sort(key=lambda x: x["relevance_score"], reverse=True)
    
    return filtered


def extract_team_mentions(text: str) -> List[str]:
    """
    Extract team names from text
    
    Simple heuristic: capitalized words 2+ chars (may need improvement)
    Better: use a team name dictionary
    """
    # This is a placeholder - should use actual team name list
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    
    # Common false positives
    stopwords = {"The", "A", "An", "In", "On", "At", "Football", "Premier", "League"}
    
    teams = [w for w in words if w not in stopwords and len(w) > 2]
    
    return list(set(teams))[:5]  # Max 5 teams


def get_breaking_news(max_age_hours: int = 6, min_relevance: int = 1) -> List[Dict]:
    """
    Fetch and filter breaking news from all RSS sources
    
    Args:
        max_age_hours: Only return news from last N hours
        min_relevance: Minimum keyword match count
    
    Returns:
        List of relevant news items with source tag
    """
    all_news = []
    
    for source_name, feed_url in RSS_FEEDS.items():
        items = fetch_rss_feed(feed_url, max_age_hours=max_age_hours)
        
        # Tag with source
        for item in items:
            item["source"] = source_name
        
        all_news.extend(items)
        
        # Be nice to RSS servers
        time.sleep(0.5)
    
    # Filter important
    important = filter_important_news(all_news)
    
    # Add team extraction
    for item in important:
        text = item.get("title", "") + " " + item.get("summary", "")
        item["mentioned_teams"] = extract_team_mentions(text)
    
    # Filter by min relevance
    important = [item for item in important if item.get("relevance_score", 0) >= min_relevance]
    
    return important


def format_news_summary(news_items: List[Dict], max_items: int = 10) -> str:
    """Format news items for Telegram/console output"""
    if not news_items:
        return "No breaking news found."
    
    lines = [f"BREAKING NEWS ({len(news_items)} items):"]
    lines.append("=" * 50)
    
    for idx, item in enumerate(news_items[:max_items], 1):
        title = item.get("title", "No title")
        source = item.get("source", "unknown").upper()
        score = item.get("relevance_score", 0)
        teams = ", ".join(item.get("mentioned_teams", [])[:3])
        
        lines.append(f"{idx}. [{source}] {title}")
        if teams:
            lines.append(f"   Teams: {teams}")
        lines.append(f"   Relevance: {score} | {item.get('link', '')}")
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("Fetching breaking football news...")
    news = get_breaking_news(max_age_hours=12, min_relevance=1)
    print(format_news_summary(news, max_items=15))
