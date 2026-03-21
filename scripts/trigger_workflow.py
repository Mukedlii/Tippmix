#!/usr/bin/env python3
"""Trigger AI Tipster System workflow manually"""
import sys
import io
import requests

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"
WORKFLOW_FILE = "ai_tipster_system.yml"

print("\n🚀 Triggering AI Tipster System workflow...\n")

# Ask which task to run
print("Select task:")
print("  1. all         - Run all tasks (full cycle)")
print("  2. aggregate   - Data aggregation only")
print("  3. results     - Fetch results only")
print("  4. settle      - Settle tips only")
print("  5. ai          - AI analysis only")
print("  6. alert       - Send TOP 6 alert only")
print("  7. recap       - Send daily recap only")
print()

choice = input("Enter number (default: 1 for all): ").strip() or "1"

task_map = {
    "1": "all",
    "2": "aggregate",
    "3": "results",
    "4": "settle",
    "5": "ai",
    "6": "alert",
    "7": "recap"
}

task = task_map.get(choice, "all")

print(f"\n✅ Selected task: {task}\n")

# Trigger workflow
url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

payload = {
    "ref": "main",
    "inputs": {
        "task": task
    }
}

print("📡 Sending request to GitHub API...")

response = requests.post(url, headers=headers, json=payload)

if response.status_code == 204:
    print("✅ Workflow triggered successfully!\n")
    print("🔗 Check status:")
    print(f"   https://github.com/{REPO}/actions\n")
    print("⏳ Workflow will start in a few seconds...")
    print("   Refresh the Actions page to see it running.\n")
elif response.status_code == 404:
    print(f"❌ Error 404: Workflow not found")
    print(f"   Make sure '{WORKFLOW_FILE}' exists in .github/workflows/\n")
    print(f"Response: {response.text}\n")
else:
    print(f"❌ Error {response.status_code}: {response.text}\n")
