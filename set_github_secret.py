#!/usr/bin/env python3
"""
Set GitHub secret via API (without gh CLI)
Uses libsodium-compatible encryption (via nacl library)
"""
import requests
import base64
import sys
import os

# Try to import nacl for encryption
try:
    from nacl import encoding, public
except ImportError:
    print("ERROR: PyNaCl not installed")
    print("Install: pip install PyNaCl")
    sys.exit(1)

GITHUB_TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()
REPO = "Mukedlii/Tippmix"
SECRET_NAME = "TELEGRAM_VIP_CHAT_ID"
SECRET_VALUE = (os.getenv(SECRET_NAME) or "").strip()
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN environment variable is required.")
if not SECRET_VALUE:
    raise RuntimeError(f"{SECRET_NAME} environment variable is required.")

print(f"Setting GitHub secret: {SECRET_NAME}")

# Get repository public key
headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

key_url = f"https://api.github.com/repos/{REPO}/actions/secrets/public-key"
r = requests.get(key_url, headers=headers)

if r.status_code != 200:
    print(f"Error getting public key: {r.status_code}")
    print(r.text)
    sys.exit(1)

key_data = r.json()
public_key = key_data['key']
key_id = key_data['key_id']

print(f"Got public key: {key_id}")

# Encrypt secret
public_key_bytes = base64.b64decode(public_key)
sealed_box = public.SealedBox(public.PublicKey(public_key_bytes))
encrypted = sealed_box.encrypt(SECRET_VALUE.encode("utf-8"))
encrypted_value = base64.b64encode(encrypted).decode("utf-8")

# Set secret
secret_url = f"https://api.github.com/repos/{REPO}/actions/secrets/{SECRET_NAME}"
payload = {
    "encrypted_value": encrypted_value,
    "key_id": key_id
}

r = requests.put(secret_url, headers=headers, json=payload)

if r.status_code in (201, 204):
    print(f"[OK] Secret {SECRET_NAME} set successfully!")
else:
    print(f"Error setting secret: {r.status_code}")
    print(r.text)
    sys.exit(1)
