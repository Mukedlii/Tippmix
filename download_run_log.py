#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import sys
import io
import zipfile
from io import BytesIO

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"
RUN_ID = "23371925073"  # Run #4

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

print(f"📥 Downloading logs for Run #{RUN_ID}...")

# Download logs
url = f"https://api.github.com/repos/{REPO}/actions/runs/{RUN_ID}/logs"
r = requests.get(url, headers=headers)

if r.status_code != 200:
    print(f"❌ Error: {r.status_code}")
    sys.exit(1)

# Extract zip
z = zipfile.ZipFile(BytesIO(r.content))

# Find the main step log
for name in z.namelist():
    if 'Combined Tipster Consensus' in name or 'tipster' in name.lower():
        print(f"\n📄 {name}\n")
        print(z.read(name).decode('utf-8'))
        break
else:
    # Print all files
    print("Files in log:")
    for name in z.namelist():
        print(f"  - {name}")
