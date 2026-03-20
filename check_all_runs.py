#!/usr/bin/env python3
"""
Check all recent workflow runs
"""
import requests

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# Get latest 20 runs
runs_url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=20"
r = requests.get(runs_url, headers=headers)

if r.status_code != 200:
    print(f"Error: {r.status_code}")
    exit(1)

runs = r.json()['workflow_runs']

print(f"\nLast 20 workflow runs:")
print("="*70)

for run in runs:
    name = run['name']
    status = run['status']
    conclusion = run.get('conclusion', 'running')
    created = run['created_at'][11:19]  # Just time
    
    icon = "[OK]" if conclusion == "success" else "[!!]" if conclusion == "failure" else "[..]"
    
    print(f"{icon} {created} | {name[:40]:<40} | {status}/{conclusion}")
