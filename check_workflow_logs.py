#!/usr/bin/env python3
"""
Check latest workflow run logs
"""
import requests
import sys
import os

GITHUB_TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()
REPO = "Mukedlii/Tippmix"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# Get latest run
runs_url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1"
r = requests.get(runs_url, headers=headers)

if r.status_code != 200:
    print(f"Error: {r.status_code}")
    sys.exit(1)

runs = r.json()['workflow_runs']
if not runs:
    print("No runs found")
    sys.exit(1)

run = runs[0]
print(f"\nLatest run: {run['name']}")
print(f"Status: {run['status']}")
print(f"Conclusion: {run.get('conclusion', 'running')}")
print(f"Created: {run['created_at']}")
print(f"Updated: {run['updated_at']}")
print(f"URL: {run['html_url']}")

# Get jobs
jobs_url = run['jobs_url']
r = requests.get(jobs_url, headers=headers)

if r.status_code != 200:
    print(f"\nError getting jobs: {r.status_code}")
    sys.exit(1)

jobs = r.json()['jobs']
print(f"\nJobs: {len(jobs)}")

for job in jobs:
    print(f"\n  Job: {job['name']}")
    print(f"  Status: {job['status']}")
    print(f"  Conclusion: {job.get('conclusion', 'running')}")
    
    # Get steps
    for step in job['steps']:
        name = step['name']
        status = step['status']
        conclusion = step.get('conclusion', 'running')
        
        if conclusion in ('failure', 'cancelled'):
            print(f"    ❌ {name}: {conclusion}")
        elif status == 'completed':
            print(f"    ✓ {name}")
