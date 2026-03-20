#!/usr/bin/env python3
"""
Download workflow logs and search for DEBUG
"""
import requests
import zipfile
import io

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# Get latest run
runs_url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1"
r = requests.get(runs_url, headers=headers)
runs = r.json()['workflow_runs']

if not runs:
    print("No runs found")
    exit(1)

run = runs[0]
print(f"Latest run: {run['name']}")
print(f"Status: {run['status']}/{run.get('conclusion')}")
print(f"Created: {run['created_at']}")

# Download logs
logs_url = run['logs_url']
print(f"\nDownloading logs from: {logs_url}")

r = requests.get(logs_url, headers=headers)

if r.status_code != 200:
    print(f"Error downloading logs: {r.status_code}")
    exit(1)

# Extract zip
z = zipfile.ZipFile(io.BytesIO(r.content))
print(f"\nLog files: {z.namelist()}")

# Find main job log
for name in z.namelist():
    if 'morning' in name.lower():
        print(f"\n{'='*70}")
        print(f"Reading: {name}")
        print('='*70)
        
        content = z.read(name).decode('utf-8', errors='ignore')
        
        # Search for DEBUG lines
        debug_lines = [line for line in content.split('\n') if '[DEBUG]' in line or 'theoddsapi' in line]
        
        if debug_lines:
            print("\nDEBUG OUTPUT:")
            for line in debug_lines[-30:]:  # Last 30 debug lines
                print(line)
        else:
            print("\nNo [DEBUG] lines found!")
            
            # Search for odds-related lines
            print("\nSearching for 'odds' mentions:")
            odds_lines = [line for line in content.split('\n') if 'odds' in line.lower()]
            for line in odds_lines[-20:]:
                print(line)
