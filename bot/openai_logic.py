import os
import json
import datetime
from typing import List, Dict, Any
from openai import OpenAI

# Max hány meccset küldünk át egyszerre az OpenAI-nak (token-kímélő)
MAX_MATCHES_FOR_OPENAI = 25

# Új stílusú OpenAI kliens (openai>=1.0)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """\
Te egy profi sportfogadási elemző vagy, a 'SZELVÉNYKIRÁLY' Telegram csatorna AI szakértője.

A bemenet egy meccslista, több sporttal:
- sport: pl. "football", "basketball"
- league
- home, away
- start_time (ISO dátum-idő string)

FELADAT:
- Az adott meccslistából válaszd ki a legígéretesebb tippeket.
- Dolgozhatsz több sporttal: főleg foci (football) és kosár (basketball).
- Használj józan, statisztikus gondolkodást: hazai pálya, forma, erőviszonyok, liga szintje, tipikus gól/ponterő stb.
- NE találj ki konkrét sérült játékosneveket, kezdőcsapatot vagy valós időjárási adatot.
  Beszélhetsz általánosan (pl. "jobb forma", "sok gólos csapat", "stabil hazai pálya"),
  de ne állíts olyat, ami biztosan hamis lehet (pl. konkrét sérült neve).

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
  - ha kevés a meccs, kevesebb tipp is lehet, de törekedj min. 3–5-re
  - NE hagyd üresen a vip_bets listát, ha kaptál meccslistát.

Minden tipphez adj:
  - sport
  - league
  - match (pl. "Liverpool - Manchester United")
  - pick (pl. "Liverpool győzelem" vagy "Over 2.5 gól")
  - odds (számként, pl. 1.65 – ha nem tudsz reális számot adni, hagyd ki vagy írj None-t)
  - reason (1-2 mondatos, érthető, modern indoklás)

A KIMENET legyen SZIGORÚAN JSON objektum, a következő kulcsokkal:
- public_bets: lista (a nyilvános szelvény tippjei)
- vip_bets: lista (a VIP szelvény tippjei)
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
    Szűrés + limit:
    - kidobjuk a barátságos / utánpótlás / női ligákat,
    - a fontosabb ligákat előrevesszük,
    - max MAX_MATCHES_FOR_OPENAI meccset hagyunk meg.
    """
    preferred = []
    others = []

    for m in matches:
        league_name = (m.get("league") or "").lower()

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


def _slim_match(m: Dict[str, Any]) -> Dict[str, Any]:
    """
    Csak a legfontosabb mezőket küldjük az OpenAI-nak (token-kímélő).
    A mélyebb statisztikai logikát a modell általános tudására bízzuk.
    """
    return {
        "sport": m.get("sport"),
        "league": m.get("league"),
        "home": m.get("home"),
        "away": m.get("away"),
        "start_time": m.get("start_time"),
    }


def _format_telegram_public(bets: List[Dict[str, Any]]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    header = (
        f"👑 SZELVÉNYKIRÁLY – NAPI INGYENES TIPPEK 👑\n"
        f"({today} – max 3 átgondolt meccs)\n\n"
    )

    if not bets:
        body = (
            "Ma nem találtam igazán stabil szelvényt a nyilvános csatornára. "
            "Inkább kihagyjuk, mint hogy erőltessük a játékot. 🤝"
        )
        return header + body

    body_lines = ["✅ Mai FREE tippek:\n"]
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

        line = f"{emoji} {idx}. {match}"
        if league:
            line += f"  ·  {league}"
        line += f"\n   Tipp: {pick}"
        if odds:
            line += f"  ·  Odd: {odds:.2f}"
        if reason:
            line += f"\n   Miért? {reason}"
        body_lines.append(line + "\n")

    total_odds = _combined_odds(bets)
    if total_odds:
        example_stake = 2000
        possible_win = total_odds * example_stake
        body_lines.append("────────────")
        body_lines.append(f"Összodds (kb.): {total_odds:.2f}")
        body_lines.append(f"Példa tét: {_format_ft(example_stake)}")
        body_lines.append(f"Várható nyeremény: kb. {_format_ft(possible_win)} 💰")

    body_lines.append(
        "\n⚠️ A sportfogadás kockázatos, játssz mindig felelősséggel, bankroll-menedzsmenttel! 🍀"
    )

    return header + "\n".join(body_lines)


def _format_telegram_vip(bets: List[Dict[str, Any]]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    n = len(bets)
    header = (
        f"🔥 SZELVÉNYKIRÁLY VIP – MAI KOMBI 🔥\n"
        f"({today} – {n} gondosan válogatott meccs)\n\n"
    )

    if not bets:
        body = (
            "Ma technikai hiba miatt nem sikerült VIP tipplistát generálni. "
            "Nem erőltetek gyenge szelvényt – holnap újra nekimegyünk, király! 🤝"
        )
        return header + body

    intro = (
        "Ma este a VIP szelvényen olyan meccsek vannak, ahol a statisztika, forma és erőviszonyok alapján "
        "reális value-t látok. Íme a mai pakk:\n"
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

        block = f"{emoji} {idx}. {match}"
        if league:
            block += f"  ·  {league}"
        block += f"\n   Tipp: {pick}"
        if odds:
            block += f"  ·  Odd: {odds:.2f}"
        if reason:
            block += f"\n   Miért? {reason}"
        lines.append(block + "\n")

    total_odds = _combined_odds(bets)
    if total_odds:
        example_stake = 5000
        possible_win = total_odds * example_stake
        lines.append("────────────")
        lines.append(f"VIP összodds: kb. {total_odds:.2f}")
        lines.append(f"Példa tét: {_format_ft(example_stake)}")
        lines.append(f"Várható nyeremény: kb. {_format_ft(possible_win)} 💰")

    lines.append(
        "\n💡 Tipp: ne játssz rá minden bankot egyetlen kombira. "
        "Kezeld a VIP szelvényt hosszú távú stratégiaként, felelős tétekkel. 🍀"
    )

    return header + "\n".join(lines)


def _fallback_simple_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Ha az OpenAI API meghal (rate limit, hálózati hiba stb.),
    akkor egy nagyon egyszerű, de mindig működő szabály-alapú fallback:
    - első 3 meccs -> public
    - első 6 meccs -> vip (ha van annyi)
    Itt nincs odds, csak irány (hazai / vendég).
    """
    simple_bets = []

    for m in matches[:6]:
        sport = m.get("sport") or "football"
        league = m.get("league") or ""
        home = m.get("home") or "Hazai csapat"
        away = m.get("away") or "Vendég csapat"

        # nagyon naiv logika: hazai győzelem
        pick = f"{home} győzelem"
        reason = "Hazai pálya előnye és az alap erőviszonyok alapján ez tűnik biztonságosabb opciónak."

        simple_bets.append(
            {
                "sport": sport,
                "league": league,
                "match": f"{home} - {away}",
                "pick": pick,
                "odds": None,
                "reason": reason,
            }
        )

    public_bets = simple_bets[:3]
    vip_bets = simple_bets

    telegram_public_text = _format_telegram_public(public_bets)
    telegram_vip_text = _format_telegram_vip(vip_bets)

    return {
        "public_bets": public_bets,
        "vip_bets": vip_bets,
        "telegram_public_text": telegram_public_text,
        "telegram_vip_text": telegram_vip_text,
    }


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    OpenAI-t használva kiválasztjuk a tippeket, és MEGFORMÁZZUK a Telegram-szöveget.
    - Token-kímélő: max 25 rövidített meccs megy az OpenAI-hoz.
    - Ha OpenAI-oldali limit / hiba van, fallback egyszerű tippre,
      hogy MINDIG legyen valami játszható.
    """
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

    selected_matches = _filter_and_limit_matches(matches)
    if not selected_matches:
        selected_matches = matches[:MAX_MATCHES_FOR_OPENAI]

    slimmed = [_slim_match(m) for m in selected_matches]
    print(f"OpenAI felé küldött meccsek száma: {len(slimmed)}")

    user_content = {
        "risk_profile_public": "közepes",
        "risk_profile_vip": "közepes-agresszív",
        "max_public_picks": 3,
        "min_vip_picks": 5,
        "max_vip_picks": 8,
        "matches": slimmed,
    }

    user_message = json.dumps(user_content, ensure_ascii=False)

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # olcsó, gyors, elég okos sport-tipp logikára
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
    except Exception as e:
        # Ha OpenAI oldalon limit vagy más hiba van:
        print(f"OpenAI API error, fallback simple tips: {repr(e)}")
        return _fallback_simple_tips(matches)

    raw = response.choices[0].message.content

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("JSON decode error az OpenAI válasznál, fallback simple tips.")
        return _fallback_simple_tips(matches)

    public_bets = data.get("public_bets") or []
    vip_bets = data.get("vip_bets") or []

    # Ha üres a VIP lista, de van public, akkor legalább azt használd VIP-nek is
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
