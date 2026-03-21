#!/usr/bin/env python3
"""
Nemzeti Sport Scraper

Scrapes Hungarian sports news site for:
- Match predictions/analysis
- Expert opinions
- Statistics
- Injury news

URL: https://www.nemzetisport.hu/
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re

BASE_URL = "https://www.nemzetisport.hu"

def scrape_football_section(days_back: int = 1) -> List[Dict]:
    """
    Scrape football section for match analysis and predictions
    
    Args:
        days_back: How many days to look back
    
    Returns:
        List of articles with predictions/analysis
    """
    
    articles = []
    
    try:
        # Football section URL
        url = f"{BASE_URL}/labdarugas"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            print(f"[Nemzeti Sport] HTTP {resp.status_code}")
            return []
        
        soup = BeautifulSoup(resp.content, 'lxml')
        
        # Find article links (adjust selectors based on actual site structure)
        article_elements = soup.find_all('article', class_='article-card')
        
        for article in article_elements[:20]:  # Latest 20 articles
            try:
                title_elem = article.find('h2') or article.find('h3')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                
                # Look for prediction/analysis keywords
                keywords = [
                    'tipp', 'előzetes', 'elemzés', 'előrejelzés',
                    'meccs előtt', 'várakozás', 'esélyesek',
                    'fogadás', 'odds', 'prognózis'
                ]
                
                if not any(kw in title.lower() for kw in keywords):
                    continue
                
                link_elem = article.find('a', href=True)
                if not link_elem:
                    continue
                
                article_url = link_elem['href']
                if not article_url.startswith('http'):
                    article_url = BASE_URL + article_url
                
                # Get publication date
                date_elem = article.find('time')
                pub_date = None
                if date_elem:
                    pub_date = date_elem.get('datetime') or date_elem.get_text(strip=True)
                
                articles.append({
                    'title': title,
                    'url': article_url,
                    'published_at': pub_date,
                    'source': 'Nemzeti Sport'
                })
                
            except Exception as e:
                print(f"[Nemzeti Sport] Error parsing article: {e}")
                continue
        
        print(f"[Nemzeti Sport] Found {len(articles)} relevant articles")
        
        return articles
        
    except Exception as e:
        print(f"[Nemzeti Sport] Error: {e}")
        return []


def extract_article_predictions(article_url: str) -> Optional[Dict]:
    """
    Extract match predictions from article content
    
    Args:
        article_url: Full URL to article
    
    Returns:
        Parsed predictions/analysis
    """
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        resp = requests.get(article_url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.content, 'lxml')
        
        # Get article body
        article_body = soup.find('div', class_='article-body') or soup.find('article')
        
        if not article_body:
            return None
        
        text = article_body.get_text()
        
        # Extract match info (e.g., "Ferencváros - Újpest")
        match_pattern = r'([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű\s]+)\s*[-–]\s*([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű\s]+)'
        matches = re.findall(match_pattern, text)
        
        # Extract prediction/opinion
        prediction_patterns = [
            r'(hazai|vendég|döntetlen)\s*győzelem',
            r'várható eredmény:\s*(\d+-\d+)',
            r'tipp:\s*(.+?)(?:\.|$)',
            r'esélyesebb.*?([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű\s]+)',
        ]
        
        predictions = []
        for pattern in prediction_patterns:
            found = re.findall(pattern, text.lower())
            predictions.extend(found)
        
        if not matches:
            return None
        
        return {
            'article_url': article_url,
            'matches_mentioned': matches,
            'predictions': predictions,
            'full_text': text[:1000],  # First 1000 chars for AI analysis
            'extracted_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"[Nemzeti Sport] Error extracting predictions: {e}")
        return None


def get_expert_analysis() -> List[Dict]:
    """
    Get expert analysis from Nemzeti Sport
    
    Returns:
        List of expert predictions with context
    """
    
    articles = scrape_football_section(days_back=1)
    
    expert_data = []
    
    for article in articles:
        predictions = extract_article_predictions(article['url'])
        
        if predictions:
            expert_data.append({
                'source': 'Nemzeti Sport',
                'article_title': article['title'],
                'article_url': article['url'],
                'published_at': article.get('published_at'),
                'matches': predictions.get('matches_mentioned', []),
                'predictions': predictions.get('predictions', []),
                'context': predictions.get('full_text', '')
            })
    
    return expert_data


# AI Analysis Integration
def analyze_with_ai(expert_data: List[Dict], ai_client) -> List[Dict]:
    """
    Send Nemzeti Sport analysis to AI for structured extraction
    
    Args:
        expert_data: Raw expert analysis
        ai_client: Anthropic/OpenAI client
    
    Returns:
        Structured predictions
    """
    
    results = []
    
    for data in expert_data:
        prompt = f"""
Elemezd ezt a Nemzeti Sport cikket és vond ki a fogadási tippeket:

Cím: {data['article_title']}
Szöveg: {data['context']}

Keresett információ:
1. Meccs (csapatok)
2. Tipp (hazai/vendég/döntetlen/gólok)
3. Indoklás (miért)
4. Bizalom (1-5)

JSON válasz:
{{
  "match": "Ferencváros vs Újpest",
  "home_team": "Ferencváros",
  "away_team": "Újpest",
  "prediction": "home_win",
  "reasoning": "Ferencváros jobb formában...",
  "confidence": 4,
  "expert": "Nemzeti Sport"
}}

Ha nincs konkrét tipp, válaszolj: {{"no_prediction": true}}
"""
        
        # Call AI (Claude/GPT)
        try:
            response = ai_client.complete(prompt)
            structured = parse_ai_response(response)
            
            if structured and not structured.get('no_prediction'):
                results.append(structured)
        
        except Exception as e:
            print(f"[Nemzeti Sport AI] Error: {e}")
            continue
    
    return results


def parse_ai_response(response: str) -> Optional[Dict]:
    """Parse AI JSON response"""
    import json
    try:
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass
    return None


# Example usage
if __name__ == "__main__":
    print("🇭🇺 Nemzeti Sport Scraper Test\n")
    
    articles = scrape_football_section()
    print(f"\nFound {len(articles)} articles")
    
    for article in articles[:3]:
        print(f"\n📰 {article['title']}")
        print(f"   {article['url']}")
        
        predictions = extract_article_predictions(article['url'])
        if predictions:
            print(f"   Matches: {predictions['matches_mentioned']}")
            print(f"   Predictions: {predictions['predictions']}")
