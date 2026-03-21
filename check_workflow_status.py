#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check latest workflow run status
"""
import requests
import sys
import io
import time

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"
WORKFLOW_FILE = "reddit_consensus.yml"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

# Get latest run
url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1"
r = requests.get(url, headers=headers)

if r.status_code != 200:
    print(f"❌ Error: {r.status_code}")
    sys.exit(1)

runs = r.json()['workflow_runs']
if not runs:
    print("No runs found")
    sys.exit(0)

run = runs[0]
status = run['status']
conclusion = run['conclusion']
created = run['created_at']
run_number = run['run_number']
html_url = run['html_url']

print(f"🔄 Run #{run_number}")
print(f"Status: {status}")
if conclusion:
    print(f"Conclusion: {conclusion}")
print(f"Created: {created}")
print(f"URL: {html_url}")
print("")

if status == 'completed':
    if conclusion == 'success':
        print("✅ SIKERES!")
    else:
        print(f"❌ Failed: {conclusion}")
else:
    print("⏳ Még fut...")
