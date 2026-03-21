#!/usr/bin/env python3
"""Update OpenAI API Key in GitHub Secrets"""
import sys
import io
import requests
import base64

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Try to import nacl for encryption
try:
    from nacl import encoding, public
except ImportError:
    print("❌ PyNaCl not installed")
    print("   Install: pip install PyNaCl")
    sys.exit(1)

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"
SECRET_NAME = "OPENAI_API_KEY"
SECRET_VALUE = "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"

print(f"\n🔑 Updating GitHub secret: {SECRET_NAME}\n")

# Get repository public key
headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

print("📡 Getting repository public key...")
key_url = f"https://api.github.com/repos/{REPO}/actions/secrets/public-key"
r = requests.get(key_url, headers=headers)

if r.status_code != 200:
    print(f"❌ Error getting public key: {r.status_code}")
    print(r.text)
    sys.exit(1)

key_data = r.json()
public_key = key_data['key']
key_id = key_data['key_id']

print(f"✅ Got public key: {key_id}\n")

# Encrypt secret
print("🔒 Encrypting API key...")
public_key_bytes = base64.b64decode(public_key)
sealed_box = public.SealedBox(public.PublicKey(public_key_bytes))
encrypted = sealed_box.encrypt(SECRET_VALUE.encode("utf-8"))
encrypted_value = base64.b64encode(encrypted).decode("utf-8")

print("✅ Encrypted\n")

# Set secret
print(f"📤 Updating {SECRET_NAME}...")
secret_url = f"https://api.github.com/repos/{REPO}/actions/secrets/{SECRET_NAME}"
payload = {
    "encrypted_value": encrypted_value,
    "key_id": key_id
}

r = requests.put(secret_url, headers=headers, json=payload)

if r.status_code in (201, 204):
    print(f"✅ Secret {SECRET_NAME} updated successfully!\n")
    print("🎉 OpenAI API key is now active in GitHub Secrets!")
    print("   AI consensus analysis will work in workflows!\n")
else:
    print(f"❌ Error setting secret: {r.status_code}")
    print(r.text)
    sys.exit(1)
