import requests
import json
import os

api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
if not api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is required.")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Say: test"}],
    "max_tokens": 5
}

try:
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=data,
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✓ SUCCESS: {result['choices'][0]['message']['content']}")
    else:
        print(f"\n✗ ERROR: {response.json()}")
        
except Exception as e:
    print(f"Exception: {e}")
