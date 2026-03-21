#!/usr/bin/env python3
"""
Set GitHub secret via API (without gh CLI)
Uses libsodium-compatible encryption (via nacl library)
"""
import requests
import base64
import sys

# Try to import nacl for encryption
try:
    from nacl import encoding, public
except ImportError:
    print("ERROR: PyNaCl not installed")
    print("Install: pip install PyNaCl")
    sys.exit(1)

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"
SECRET_NAME = "TELEGRAM_SESSION_STRING"
SECRET_VALUE = "1BJWap1wBu7ITLUiFdktD4rIP4GlHznNAxJX81Cx5U5Lds_cA6tYt9M-FWpdKTCemMZthIspKeBTS9pNWBB4xvxZwFNvntF3frrW5MSXI1_QE97DWtVo4JK7-ObyYvdNCmMBXitdxZ-Apbp3IeLX5krOLm3qf6S5PKpmNRXdHu5anbt26pIS6ss3Pxd1ldKjlY4xdVW6wiHywSPUpVjr-YN7jfiI79vDxn7Hykr4JKVEh6T8cBmJjDvh_fZRYpiEi5zgAkcR59d8AHfQ4ETZoaUM_XYKYgce2GL4Qai2N7kAykGoooeUHzT1iz4FumszjiKVZiFbnkL68z5qyYDfpdaF4ww_3k7w="

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
