import requests
import json

api_key = "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"

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
