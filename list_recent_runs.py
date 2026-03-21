#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import sys
import io

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

url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=5"
r = requests.get(url, headers=headers)

runs = r.json()['workflow_runs']

print(f"📊 Legutóbbi 5 run:\n")
for run in runs:
    status = run['status']
    conclusion = run['conclusion'] or '---'
    created = run['created_at']
    run_number = run['run_number']
    event = run['event']
    
    emoji = "✅" if conclusion == "success" else ("❌" if conclusion == "failure" else "⏳")
    
    print(f"{emoji} Run #{run_number} ({event})")
    print(f"   Created: {created}")
    print(f"   Status: {status} / {conclusion}")
    print(f"   URL: {run['html_url']}")
    print()
