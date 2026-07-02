#!/usr/bin/env python3
import requests
import os

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = "-1003341312269"

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required.")

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": "🧪 TEST: Bot működik! Ha ezt látod, minden rendben! ✅"
}

r = requests.post(url, json=payload, timeout=15)
print(f"Status: {r.status_code}")
print(f"Response: {r.json()}")
