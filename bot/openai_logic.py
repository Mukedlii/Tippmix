import os
import json
import datetime
from typing import List, Dict, Any
from openai import OpenAI

# Max hány meccset küldünk át egyszerre az OpenAI-nak
MAX_MATCHES_FOR_OPENAI = 80

# Új stílusú OpenAI kliens (openai>=1.0)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
  - ha kevés a meccs, kevesebb tipp is lehet, de akkor is törekedj min. 3–5-re
  - NE hagyd üresen a vip_bets listát, ha kaptál meccslistát.

Mindig:
- Minden tipphez adj:
  - sport
  - league
  - match (pl. "Liverpool - Manchester United")
  - pick (pl. "Liverpool győzelem")
  - odds (számként, pl. 1.65 – NE stringként)
  - reason (1-2 mondatos magyarázat)
- NE írj Telegram szöveget, CSAK struktúrált JSON-t.

A KIMENET legyen SZIGORÚAN JSON objektum, a következő kulcsokkal:
- public_bets: lista (a nyilvános szelvény tippjei)
- vip_bets: lista (a VIP szelvény tippjei)

Egy tipp objektum PÉLDÁUL így nézzen ki:
{
  "sport": "football",
  "league": "Premier League",
  "match": "Liverpool - Manchester United",
  "pick": "Liverpool győzelem",
  "odds": 1.65,
  "reason": "Hazai pálya, jobb forma, több helyzetet alakítanak ki meccsenként."
}
"""


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _combined_odds(bets: List[Dict[str, Any]]):
    odds_values = []
    for b in bets:
        o = _safe_float(b.get("odds"))
        if o and o > 1.01:
            odds_values.append(o)
    if not odds_values:
        return None
    total = 1.0
    for o in odds_values:
        total *= o
    return total


def _format_ft(amount: float) -> str:
    n = int(round(amount))
    s = f"{n:,}".replace(",", ".")
    return f"{s} Ft"


def _filter_and_limit_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sok meccs esetén:
    - kidobjuk a barátságos / utánpótlás / női ligákat,
    - maximum MAX_MATCHES_FOR_OPENAI darabot hagyunk meg.
    Így nem küldünk túl sok tokent az OpenAI-nak (rate limit védelem).
    """
    preferred = []
    others = []

    for m in matches:
        league_name = (m.get("league") or "").lower()

        # Barátságos, utánpótlás, női ligák kiszűrése
        bad_keywords = [
            "friendly",
            "friendlies",
            "u19",
            "u20",
            "u21",
            "u17",
            "women",
            "női",
            "barátságos",
        ]
        if any(k in league_name for k in bad_keywords):
            continue

        # Topabb ligák előresorolása
        top_keywords = [
            "premier league",
            "la liga",
            "serie a",
            "bundesliga",
            "ligue 1",
            "nb i",
            "champions league",
            "europa league",
            "nba",
            "euroleague",
        ]

        if any(k in league_name for k in top_keywords):
            preferred.append(m)
        else:
            others.append(m)

    ordered = preferred + others

    if len(ordered) > MAX_MATCHES_FOR_OPENAI:
        ordered = ordered[:MAX_MATCHES_FOR_OPENAI]

    return ordered


def _format_telegram_public(bets: List[Dict[str, Any]]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    header = (
        f"👑 SZELVÉNYKIRÁLY – NAPI KOMBI 👑\n"
        f"({today} – max 3 stabil tipp)\n\n"
    )

    if not bets:
        body = "Ma nem találtam igazán stabil szelvényt a nyilvános csatornára. Inkább kihagyjuk, mint hogy erőltessük. 🤝"
        return header + body

    body_lines = ["Mai ingyenes szelvényedre ezek a meccsek fértek fel:\n"]
    for idx, b in enumerate(bets, start=1):
        sport = (b.get("sport") or "").lower()
        if sport == "football":
            emoji = "⚽"
        elif sport == "basketball":
            emoji = "🏀"
        else:
            emoji = "🎯"

        league = b.get("league") or ""
        match = b.get("match") or f"{b.get('home', '?')} vs {b.get('away', '?')}"
        pick = b.get("pick") or "Tipp hiányzik"
        odds = _safe_float(b.get("odds"))
        reason = b.get("reason") or ""

        line = f"{emoji} {idx}. Meccs: {match}"
        if league:
            line += f" ({league})"
        line += f"\n   Tipp: {pick}"
        if odds:
            line += f"\n   Odd: {odds:.2f}"
        if reason:
            line += f"\n   Indoklás: {reason}"
        body_lines.append(line + "\n")

    total_odds = _combined_odds(bets)
    if total_odds:
        example_stake = 2000  # free példatét
        possible_win = total_odds * example_stake
        body_lines.append("⸻")
        body_lines.append(f"Összodds (kb.): {total_odds:.2f}")
        body_lines.append(f"Példa tét: {_format_ft(example_stake)}")
        body_lines.append(f"Várható nyeremény: kb. {_format_ft(possible_win)} 💰")

    body_lines.append(
        "\nNe feledd, a sportfogadás kockázatos, játssz mindig felelősséggel! 🍀"
    )

    return header + "\n".join(body_lines)


def _format_telegram_vip(bets: List[Dict[str, Any]]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    n = len(bets)
    header = (
        f"👑 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI MA ESTÉRE! 👑\n"
        f"({today} – {n} meccs, nagyobb összodds, nagyobb profit potenciál)\n\n"
    )

    if not bets:
        # Ez elvileg nem fordul elő, mert generate_tips fallbackel,
        # de ha mégis, jelezzük, hogy technikai gond volt.
        body = "Technikai hiba miatt nem sikerült VIP tipplistát generálni. Próbáljuk újra legközelebb, király! 🤝"
        return header + body

    intro = (
        "Ma este a VIP szelvényen gondosan válogatott mérkőzések vannak, "
        "erős favoritokkal és statisztikai háttérrel.\n\n"
    )

    lines = [intro]

    for idx, b in enumerate(bets, start=1):
        sport = (b.get("sport") or "").lower()
        if sport == "football":
            emoji = "⚽"
        elif sport == "basketball":
            emoji = "🏀"
        else:
            emoji = "🎯"

        league = b.get("league") or ""
        match = b.get("match") or f"{b.get('home', '?')} vs {b.get('away', '?')}"
        pick = b.get("pick") or "Tipp hiányzik"
        odds = _safe_float(b.get("odds"))
        reason = b.get("reason") or ""

        block = f"{emoji} {idx}. Meccs: {match}"
        if league:
            block += f" ({league})"
        block += f"\n   Tipp: {pick}"
        if odds:
            block += f"\n   Odd: {odds:.2f}"
        if reason:
            block += f"\n   Indoklás: {reason}"
        lines.append(block + "\n")

    total_odds = _combined_odds(bets)
    if total_odds:
        example_stake = 5000
        possible_win = total_odds * example_stake
        lines.append("⸻")
        lines.append(f"VIP összodds: kb. {total_odds:.2f}")
        lines.append(f"Példa tét: {_format_ft(example_stake)}")
        lines.append(f"Várható nyeremény: kb. {_format_ft(possible_win)} 💰")

    lines.append(
        "\nNe feledd, a sportfogadás kockázatos, játssz mindig felelősséggel, "
        "és csak annyit kockáztass, amennyit megengedhetsz magadnak! 🍀"
    )

    return header + "\n".join(lines)


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    OpenAI-t használva kiválasztjuk a tippeket, és MEGFORMÁZZUK a Telegram-szöveget.
    LOGIKA: ha van bármennyi meccs, MINDIG legyen legalább néhány tipp.
    """
    if not matches:
        # Extrém eset: semmi meccs
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

    # Meccsek szűrése és limitálása, hogy ne szálljunk el tokenben
    selected_matches = _filter_and_limit_matches(matches)
    print(f"OpenAI felé küldött meccsek száma: {len(selected_matches)}")

    if not selected_matches:
        # Ha valamiért minden kiszűrődött, akkor vegyük az első X meccset nyersen
        selected_matches = matches[:MAX_MATCHES_FOR_OPENAI]

    user_content = {
        "risk_profile_public": "közepes",
        "risk_profile_vip": "közepes-agresszív",
        "max_public_picks": 3,
        "min_vip_picks": 5,
        "max_vip_picks": 8,
        "matches": selected_matches,
    }

    user_message = json.dumps(user_content, ensure_ascii=False)

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    raw = response.choices[0].message.content

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "public_bets": [],
            "vip_bets": [],
            "telegram_public_text": "Hiba történt a nyilvános szelvény generálásánál.",
            "telegram_vip_text": "Hiba történt a VIP szelvény generálásánál.",
        }

    public_bets = data.get("public_bets") or []
    vip_bets = data.get("vip_bets") or []

    # 🔥 FONTOS: ha valamiért üres a VIP lista, de vannak meccsek,
    # NE maradjon üres, használjuk legalább a public tippeket VIP-nek is.
    if not vip_bets and public_bets:
        vip_bets = public_bets[:]

    telegram_public_text = _format_telegram_public(public_bets)
    telegram_vip_text = _format_telegram_vip(vip_bets)

    return {
        "public_bets": public_bets,
        "vip_bets": vip_bets,
        "telegram_public_text": telegram_public_text,
        "telegram_vip_text": telegram_vip_text,
    }
