"""
GitHub Secret hozzáadása (ODDS_API_KEY)

1. Menj: https://github.com/settings/tokens
2. Generate token: classic token, select 'repo' scope
3. Másold ki a tokent
4. Futtasd: python add_secret.py <YOUR_TOKEN>
"""

import sys
import requests
import base64
from nacl import encoding, public

REPO_OWNER = "Mukedlii"
REPO_NAME = "Tippmix"
SECRET_NAME = "ODDS_API_KEY"
SECRET_VALUE = "acf78bce7a7976c2bc4d028528d4cb2f"

def add_secret(github_token):
    # 1. Get public key
    url_key = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/secrets/public-key"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    resp = requests.get(url_key, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Hiba public key lekérésnél: {resp.status_code}")
        print(resp.text)
        return False
    
    public_key_data = resp.json()
    public_key = public_key_data["key"]
    key_id = public_key_data["key_id"]
    
    # 2. Encrypt secret
    public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(SECRET_VALUE.encode("utf-8"))
    encrypted_value = base64.b64encode(encrypted).decode("utf-8")
    
    # 3. Create/update secret
    url_secret = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/secrets/{SECRET_NAME}"
    payload = {
        "encrypted_value": encrypted_value,
        "key_id": key_id
    }
    
    resp = requests.put(url_secret, headers=headers, json=payload)
    if resp.status_code in (201, 204):
        print(f"✅ Secret '{SECRET_NAME}' sikeresen hozzáadva!")
        return True
    else:
        print(f"❌ Hiba secret hozzáadásnál: {resp.status_code}")
        print(resp.text)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Használat: python add_secret.py <GITHUB_TOKEN>")
        print("\n1. Menj: https://github.com/settings/tokens")
        print("2. Generate token (classic), válaszd: 'repo' scope")
        print("3. Futtasd: python add_secret.py <token>")
        sys.exit(1)
    
    token = sys.argv[1]
    add_secret(token)
