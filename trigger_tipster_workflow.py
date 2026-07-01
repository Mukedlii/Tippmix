#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trigger Combined Tipster Consensus Alert workflow manually
"""
import requests
import sys
import io
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

GITHUB_TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()
REPO = "Mukedlii/Tippmix"
WORKFLOW_FILE = "reddit_consensus.yml"

print("🚀 Triggering Combined Tipster Consensus Alert workflow...")

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
payload = {
    "ref": "main"
}

r = requests.post(url, headers=headers, json=payload)

if r.status_code == 204:
    print("✅ Workflow triggered successfully!")
    print("")
    print("Check status:")
    print(f"https://github.com/{REPO}/actions/workflows/{WORKFLOW_FILE}")
    print("")
    print("Várható futási idő: ~2-3 perc")
    print("Eredmény: Telegram VIP csatorna (ha van consensus)")
else:
    print(f"❌ Error: {r.status_code}")
    print(r.text)
    sys.exit(1)
