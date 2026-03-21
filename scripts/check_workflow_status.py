#!/usr/bin/env python3
"""Check AI Tipster System workflow status"""
import sys
import io
import requests
from datetime import datetime

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"
WORKFLOW_FILE = "ai_tipster_system.yml"

print("\n📊 Checking workflow status...\n")

# Get workflow runs
url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

params = {
    "per_page": 5
}

response = requests.get(url, headers=headers, params=params)

if response.status_code == 200:
    data = response.json()
    runs = data.get('workflow_runs', [])
    
    if not runs:
        print("⚠️  No workflow runs found\n")
    else:
        print(f"📋 Last {len(runs)} workflow runs:\n")
        
        for i, run in enumerate(runs, 1):
            status = run['status']
            conclusion = run['conclusion']
            created = run['created_at']
            run_number = run['run_number']
            run_id = run['id']
            
            # Status emoji
            if status == 'completed':
                if conclusion == 'success':
                    emoji = "✅"
                elif conclusion == 'failure':
                    emoji = "❌"
                elif conclusion == 'cancelled':
                    emoji = "🚫"
                else:
                    emoji = "⚠️"
            elif status == 'in_progress':
                emoji = "⏳"
            elif status == 'queued':
                emoji = "🕐"
            else:
                emoji = "❓"
            
            # Format timestamp
            try:
                dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except:
                time_str = created
            
            print(f"{emoji} Run #{run_number} - {status}")
            if conclusion:
                print(f"   Result: {conclusion}")
            print(f"   Created: {time_str}")
            print(f"   🔗 https://github.com/{REPO}/actions/runs/{run_id}")
            print()
else:
    print(f"❌ Error {response.status_code}: {response.text}\n")
