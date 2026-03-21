#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup

url = "https://www.bettingexpert.com/tips/football"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

r = requests.get(url, headers=headers, timeout=20)

print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type')}")
print(f"Content length: {len(r.text)}")

soup = BeautifulSoup(r.content, 'html.parser')
print(f"Title: {soup.title.string if soup.title else 'None'}")

# Check if it's a SPA (Single Page App)
scripts = soup.find_all('script')
print(f"\nScripts: {len(scripts)}")

# Look for React/Next.js indicators
if any('react' in str(s).lower() or 'next' in str(s).lower() for s in scripts):
    print("⚠️ Site appears to be React/Next.js (client-side rendering)")
    print("   → Simple scraping won't work, need Selenium/Playwright")

# Show first 1000 chars
print(f"\nFirst 1000 chars of HTML:")
print(r.text[:1000])

# Look for any tip-related elements
tip_keywords = ['tip', 'pick', 'bet', 'prediction']
for keyword in tip_keywords:
    elements = soup.find_all(class_=re.compile(keyword, re.I))
    if elements:
        print(f"\n Found {len(elements)} elements with '{keyword}' in class")
        break
