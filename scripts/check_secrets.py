#!/usr/bin/env python3
"""Check GitHub Secrets"""
import sys
import io
import requests
import os

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

token = (os.getenv("GITHUB_TOKEN") or "").strip()
headers = {"Authorization": f"token {token}"}

response = requests.get(
    "https://api.github.com/repos/Mukedlii/Tippmix/actions/secrets",
    headers=headers
)

if response.status_code == 200:
    secrets = response.json().get('secrets', [])
    print(f"\n✅ GitHub Secrets ({len(secrets)}):\n")
    for secret in secrets:
        print(f"  - {secret['name']}")
    print()
    
    # Check for OpenAI
    has_openai = any(s['name'] == 'OPENAI_API_KEY' for s in secrets)
    if has_openai:
        print("✅ OPENAI_API_KEY found!\n")
    else:
        print("❌ OPENAI_API_KEY NOT found!\n")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
