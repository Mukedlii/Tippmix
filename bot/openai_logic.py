import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Te egy profi sportfogadási elemző vagy, a 'SZELVÉNYKIRÁLY' Telegram csatorna AI szakértője.
Feladatod:
- Az adott meccslistából válaszd ki a legígéretesebb tippeket.
- Készíts egy nyilvános szelvényt (max 3 tipp, közepes kockázat).
- Készíts egy VIP szelvényt (max 7 tipp, némileg agresszívebb kockázat).
- Mindig adj odds-ot és rövid magyarázatot (1-2 mondat).
- Stílus: magyar, laza, de profi, felelős játékra figyelmeztető.
- A kimenet legyen JSON, ami tartalmaz:
  - public_bets: lista
  - vip_bets: lista
  - telegram_public_text: string
  - telegram_vip_text: string

A meccsadatok: id, league, home, away, start_time, odds, stats.
"""


def generate_tips(matches):
    """
    OpenAI-t használva kiválasztjuk a tippeket, és megíratjuk a Telegram-posztokat.
    """
    # Előszűrés – pl. odds tartomány, hogy ne küldj be mindent
    filtered = [
        m for m in matches
        if 1.20 <= m["odds"]["home"] <= 3.00  # példa: hazai odds tartomány
    ]

    if not filtered:
        return {
            "public_bets": [],
            "vip_bets": [],
            "telegram_public_text": "Ma nem találtam értelmes szelvényt, király. 🤷‍♂️",
            "telegram_vip_text": "Ma a statok alapján nincs igazán jó VIP kombi. Inkább kihagyjuk. 🤝",
        }

    user_content = {
        "risk_profile_public": "közepes",
        "risk_profile_vip": "közepes-agresszív",
        "max_public_picks": 3,
        "max_vip_picks": 7,
        "matches": filtered,
    }

    response = client.responses.create(
        model="gpt-4.1-mini",
        reasoning={"effort": "medium"},
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )

    # A JSON válasz a first outputban lesz
    raw = response.output[0].content[0].text

    data = json.loads(raw)

    # Biztonsági fallback-ok
    data.setdefault("public_bets", [])
    data.setdefault("vip_bets", [])
    data.setdefault("telegram_public_text", "Hiba a nyilvános üzenet generálásánál.")
    data.setdefault("telegram_vip_text", "Hiba a VIP üzenet generálásánál.")

    return data
