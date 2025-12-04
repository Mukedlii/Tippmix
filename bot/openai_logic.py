import os
import json
from openai import OpenAI

# Az OPENAI_API_KEY-t automatikusan a környezeti változóból veszi (GitHub Secret)
client = OpenAI()

SYSTEM_PROMPT = """\
Te egy profi sportfogadási elemző vagy, a 'SZELVÉNYKIRÁLY' Telegram csatorna AI szakértője.
Feladatod:
- Az adott meccslistából válaszd ki a legígéretesebb tippeket.
- Készíts egy NYILVÁNOS szelvényt:
  - max 3 tippel
  - inkább biztonságosabb, stabilabb meccsekből
- Készíts egy VIP szelvényt:
  - lehetőleg 5–7 tippel (minimum 5, ha van elég értelmes meccs)
  - kicsit agresszívebb kockázat, de ne legyen teljesen őrült
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

    # Szűrés: csak olyan meccs, ahol van hazai odds, és reális tartományban van
    filtered = [
        m for m in matches
        if m.get("odds", {}).get("home") is not None
        and 1.20 <= m["odds"]["home"] <= 3.00
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
        "min_vip_picks": 5,
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

    # A válasz első outputjából olvassuk ki a JSON-t
    raw = response.output[0].content[0].text
    data = json.loads(raw)

    # Biztonsági fallbackok
    data.setdefault("public_bets", [])
    data.setdefault("vip_bets", [])
    data.setdefault("telegram_public_text", "Hiba a nyilvános üzenet generálásánál.")
    data.setdefault("telegram_vip_text", "Hiba a VIP üzenet generálásánál.")

    return data

    return data
