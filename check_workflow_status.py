#!/usr/bin/env python3
import requests
import json
from datetime import datetime

url = "https://api.github.com/repos/Mukedlii/Tippmix/actions/runs?per_page=10"
r = requests.get(url, headers={'Accept': 'application/vnd.github+json'})

if r.status_code != 200:
    print(f"Error: {r.status_code}")
    print(r.text)
    exit(1)

runs = r.json()['workflow_runs']

print("\n" + "="*70)
print("LAST 10 GITHUB ACTIONS RUNS")
print("="*70)

for run in runs:
    name = run['name']
    status = run['status']
    conclusion = run.get('conclusion', 'running')
    created = run['created_at']
    updated = run['updated_at']
    
    # Convert UTC to Budapest time (GMT+1)
    created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
    updated_dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
    
    icon = "✓" if conclusion == "success" else "✗" if conclusion == "failure" else "⏳"
    
    print(f"\n{icon} {name}")
    print(f"   Status: {status} | Conclusion: {conclusion}")
    print(f"   Created: {created_dt.strftime('%H:%M:%S')}")
    print(f"   Updated: {updated_dt.strftime('%H:%M:%S')}")
    print(f"   URL: {run['html_url']}")
