#!/usr/bin/env python3
import requests
import os

BOT_TOKEN = "8238287955:AAEo87ADOjZx6qcCW1eEYN6YV1klAzZ_8bs"
CHAT_ID = "-1003341312269"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": "🧪 TEST: Bot működik! Ha ezt látod, minden rendben! ✅"
}

r = requests.post(url, json=payload, timeout=15)
print(f"Status: {r.status_code}")
print(f"Response: {r.json()}")
