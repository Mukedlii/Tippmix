import os
import json
import openai

# A kulcsot az OPENAI_API_KEY környezeti változóból vesszük (GitHub Secret)
openai.api_key = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT = """\
Te egy profi sportfogadási elemző vagy, a 'SZELVÉNYKIRÁLY' Telegram csatorna AI szakértője.

A bemenet egy meccslista, több sporttal:
- sport: pl. "football", "basketball"
- league, country
- home, away
- start_time (ISO dátum-idő string)
- odds: home, away, draw (lehetnek None, ha nincs valós odds)
- stats: extra infók (league_id stb.)

Feladatod:
- Az adott meccslistából válaszd ki a legígéretesebb tippeket.
- Dolgozhatsz több sporttal: foci (football) és kosár (basketball).
- Kerüld a teljesen random, lottó jellegű tippeket.

KÉT külön szelvényt készítesz:

1) NYILVÁNOS (FREE) szelvény:
  - max 3 tipp
  - inkább biztonságosabb meccsek
  - ha lehet, foci legyen a fókusz, de jöhet 1 kosár tipp is
  - ha nagyon kevés meccs van, akkor kevesebb tippet adj (1–2 is ok)

2) VIP szelvény:
  - lehetőleg 5–8 tipp
  - kicsit agresszívebb kockázat, de NE legyen őrült (ne 8 darab 4.50-es odds)
  - ha van elég jó meccs, próbálj több sportot keverni (foci + kosár)
  - ha kevés a meccs, kevesebb tipp is lehet, de akkor is törekedj min. 5-re

Mindig:
- Adj meg oddsot is, HA a meccs `odds` mezőjében van információ.
- Ha nincs odds, akkor vagy ne írj pontos számot, vagy csak óvatos, körülbelüli becslést adj (pl. "kb. 1.60 körüli").
- Adj rövid magyarázatot (1–2 mondat) minden tipphez: forma, erőviszonyok, motiváció stb.
- FIGYELMEZTESS a felelős játékra (pl. a szöveg végén 1 mondat).

A KIMENET legyen SZIGORÚAN JSON objektum, a következő kulcsokkal:
- public_bets: lista (a nyilvános szelvény tippjei)
- vip_bets: lista (a VIP szelvény tippjei)
- telegram_public_text: string (Telegram üzenet a sima csatornára)
- telegram_vip_text: string (Telegram üzenet a VIP csatornára)

Egy tipp objektum például így nézhet ki:
{
  "sport": "football",
  "league": "Premier League",
  "match": "Liverpool - Manchester United",
  "pick": "Liverpool győzelem",
  "odds": 1.65,
  "reason": "Hazai pálya, jobb forma, több helyzetet alakítanak ki meccsenként."
}
"""


def generate_tips(matches):
    """
    OpenAI-t használva kiválasztjuk a tippeket, és megíratjuk a Telegram-posztokat.
    LOGIKA: ha van bármennyi meccs, MINDIG generálunk tippeket.
    """

    # Ha az API SEMMILYEN meccset nem ad vissza (extrém eset),
    # akkor jelezzük, hogy technikailag nincs mit játszani.
    if not matches:
        return {
            "public_bets": [],
            "vip_bets": [],
            "telegram_public_text": (
                "Ma technikai okból az API nem adott vissza egyetlen meccset sem, "
                "ezért nem tudok felelős szelvényt összerakni. 🤷‍♂️"
            ),
            "telegram_vip_text": (
                "Ma a Sport API nem szolgáltat meccsadatot (valószínűleg válogatott szünet "
                "vagy technikai hiba), ezért nem erőltetek VIP kombit. 🤝"
            ),
        }

    # VANNAK meccsek → átadjuk az összeset az OpenAI-nak, hogy válogasson.
    filtered = matches

    user_content = {
        "risk_profile_public": "közepes",
        "risk_profile_vip": "közepes-agresszív",
        "max_public_picks": 3,
        "min_vip_picks": 5,
        "max_vip_picks": 8,
        "matches": filtered,
    }

    user_message = json.dumps(user_content, ensure_ascii=False)

    response = openai.ChatCompletion.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
    )

    raw = response.choices[0].message["content"]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Ha valamiért nem tudtuk JSON-ként beolvasni, legyen egy alap fallback
        return {
            "public_bets": [],
            "vip_bets": [],
            "telegram_public_text": "Hiba történt a nyilvános szelvény generálásánál.",
            "telegram_vip_text": "Hiba történt a VIP szelvény generálásánál.",
        }

    # Biztonsági fallbackok
    data.setdefault("public_bets", [])
    data.setdefault("vip_bets", [])
    data.setdefault("telegram_public_text", "Hiba a nyilvános üzenet generálásánál.")
    data.setdefault("telegram_vip_text", "Hiba a VIP üzenet generálásánál.")

    return data
