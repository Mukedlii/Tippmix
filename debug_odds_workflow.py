#!/usr/bin/env python3
"""
Full diagnostic of odds enrichment issue
"""
import requests
import json

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"
ODDS_API_KEY = "acf78bce7a7976c2bc4d028528d4cb2f"

print("\n" + "="*70)
print("ODDS ENRICHMENT DIAGNOSTIC")
print("="*70)

# 1. Check GitHub Secret exists
print("\n[1] Checking GitHub Secrets...")
headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

secrets_url = f"https://api.github.com/repos/{REPO}/actions/secrets"
r = requests.get(secrets_url, headers=headers)

if r.status_code == 200:
    secrets = r.json()['secrets']
    secret_names = [s['name'] for s in secrets]
    
    if 'ODDS_API_KEY' in secret_names:
        print("   ✓ ODDS_API_KEY secret exists")
    else:
        print("   ✗ ODDS_API_KEY secret NOT FOUND")
        print(f"   Available secrets: {secret_names}")
else:
    print(f"   Error: {r.status_code}")

# 2. Check TheOddsAPI quota
print("\n[2] Checking TheOddsAPI quota...")
url = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
params = {
    "apiKey": ODDS_API_KEY,
    "regions": "eu",
    "markets": "h2h",
    "oddsFormat": "decimal",
}

r = requests.get(url, params=params)
print(f"   Status: {r.status_code}")
print(f"   Remaining: {r.headers.get('x-requests-remaining', 'N/A')}")
print(f"   Used: {r.headers.get('x-requests-used', 'N/A')}")

if r.status_code == 200:
    events = r.json()
    print(f"   Events: {len(events)}")
    if events:
        event = events[0]
        print(f"   Sample: {event['home_team']} vs {event['away_team']}")
else:
    print(f"   Error: {r.text[:200]}")

# 3. Check latest workflow run logs (if possible)
print("\n[3] Checking latest workflow run...")
runs_url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1&event=workflow_dispatch"
r = requests.get(runs_url, headers=headers)

if r.status_code == 200:
    runs = r.json()['workflow_runs']
    if runs:
        run = runs[0]
        print(f"   Run: {run['name']}")
        print(f"   Status: {run['status']}/{run.get('conclusion')}")
        print(f"   Created: {run['created_at']}")
        print(f"   URL: {run['html_url']}")
        
        # Try to get logs URL (requires downloading)
        logs_url = run['logs_url']
        print(f"   Logs: {logs_url}")
        print("   (Download logs manually from GitHub Actions page)")

# 4. Check local test
print("\n[4] Local test of odds enrichment...")
print("   (Run locally with ODDS_API_KEY set)")

print("\n" + "="*70)
print("\nRECOMMENDATION:")
print("1. Download workflow logs from: https://github.com/Mukedlii/Tippmix/actions")
print("2. Search for 'theoddsapi' or 'ODDS_API_KEY' in logs")
print("3. Check if odds enrichment is running")
print("="*70)
