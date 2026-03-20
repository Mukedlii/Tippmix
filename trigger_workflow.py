#!/usr/bin/env python3
"""
Trigger GitHub Actions workflow manually
"""
import os
import sys
import requests

REPO = "Mukedlii/Tippmix"
WORKFLOW = "tippmix_morning_full.yml"
BRANCH = "main"

# Get token from environment or TOOLS.md or prompt
token = os.getenv("GITHUB_TOKEN")

if not token:
    # Try reading from workspace TOOLS.md
    tools_path = os.path.join(os.path.dirname(__file__), "..", "TOOLS.md")
    if os.path.exists(tools_path):
        with open(tools_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Extract token from markdown code block
            import re
            match = re.search(r'ghp_[A-Za-z0-9_]{36,}', content)
            if match:
                token = match.group(0)
                print(f"[Found token in TOOLS.md]")

if not token:
    print("GitHub Personal Access Token not found in environment.")
    print("")
    print("Enter your GitHub token (it won't be saved):")
    print("Create one: https://github.com/settings/tokens/new?scopes=workflow")
    print("")
    token = input("GitHub Token (ghp_...): ").strip()

if not token:
    print("Error: No token provided")
    sys.exit(1)

url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

payload = {
    "ref": BRANCH
}

print(f"Triggering workflow: {WORKFLOW} on {BRANCH}...")

try:
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 204:
        print("[OK] Workflow triggered successfully!")
        print("")
        print(f"Check status: https://github.com/{REPO}/actions")
    else:
        print(f"[!!] Unexpected response: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"[!!] Error: {e}")
    print("")
    print("Make sure your GitHub token has 'workflow' scope.")
