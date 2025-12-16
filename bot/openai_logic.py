import os
import json
import math
from typing import Any, Dict, List, Tuple

from openai import OpenAI

# OpenAI kliens – kulcs GitHub Secrets-ből jön (OPENAI_API_KEY)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------


def _format_huf(amount: float) -> str:
    """
    Egyszerű forint formázó: 123456.7 -> '123 457 Ft'
    (kerekít egészre, szóközös ezres tagolás)
    """
    rounded = int(round(amount))
    s = f"{rounded:,}".replace(",", " ")
    return f"{s} Ft"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _league_priority(league_name: str) -> int:
    """
    Soft liga-prioritás: minél KISEBB a szám, annál jobb liga.
    1–2: top / erős ligák
    3–4: normál ligák
    5–6: ifi / egzotikus / barátságos – csak nagyon erős jel esetén
    """
    if not league_name:
        return 4

    name = league_name.lower()

    # Top 5 európai ligák
    top_leagues = [
        "premier league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
    ]
    if any(x in name for x in top_leagues):
        return 1

    # Erős első osztályok, európai kupák, nagyobb ligák
    strong_patterns = [
        "champions league",
        "europa league",
        "conference league",
        "eredivisie",
        "primeira liga",
        "super lig",
        "super league",
        "jupiler pro league",
        "premier division",
        "championship",
        "serie b",
        "segunda division",
        "bundesliga 2",
        "mls",
        "allsvenskan",
        "superliga",
        "liga 1",
        "liga i",
        "liga mx",
        "premier liga",
        "pro league",
    ]
    if any(x in name for x in strong_patterns):
        return 2

    # Válogatott tornák
    national_team_patterns = [
        "world cup",
        "euro",
        "nations league",
        "copa america",
        "afcon",
        "africa cup",
        "asian cup",
        "gold cup",
    ]
    if any(x in name for x in national_team_patterns):
        return 2

    # Közepes ligák
    medium_patterns = [
        "1. lig",
        "first division",
        "liga 2",
        "segunda liga",
        "liga pro",
    ]
    if any(x in name for x in medium_patterns):
        return 3

    # Ifjúsági / barátságos / egzotikus – alacsonyabb prioritás
    low_patterns = [
        "friendly",
        "u19",
        "u20",
        "u21",
        "u22",
        "u23",
        "reserve",
        "youth",
        "cup u23",
        "arab cup",
        "yokary liga",
        "southeast asian games",
        "persian gulf pro league",
    ]
    if any(x in name for x in low_patterns):
        return 6

    return 4


def _is_forbidden_market(tip_text: str) -> bool:
    """
    Igazat ad, ha a tipp tiltott piacra utal:
    - Over/Under
    - gólszám / gólpiac
    - mindkét csapat szerez gólt / BTTS
    - dupla esély (1X, X2, 12, 'hazai vagy döntetlen', stb.)
    """
    if not tip_text:
        return True

    t = tip_text.lower()

    forbidden_substrings = [
        "over",
        "under",
        " 2.5",
        " 2,5",
        "gól felett",
        "gól alatt",
        "gólszám",
        "gólpiac",
        "mindkét csapat",
        "btts",
        "1x",
        "x2",
        " 12",
        "hazai vagy",
        "vendég vagy",
        "döntetlen vagy",
        "dupla esély",
        "draw no bet",
        "dnb",
        "handicap",
        "hendi",
        "ásiai hendikep",
    ]
    return any(p in t for p in forbidden_substrings)


def _normalize_1x2_tip(tip_text: str) -> str:
    """
    Tipp szöveg normalizálása 1X2 piacra.
    Engedélyezett formák:
      - 'Hazai győzelem'
      - 'Döntetlen'
      - 'Vendég győzelem'
    """
    if not tip_text:
        return "Hazai győzelem"

    t = tip_text.lower()

    if "döntetlen" in t and "vagy" not in t:
        return "Döntetlen"

    if "vendég" in t or "idegenben" in t or "away" in t:
        return "Vendég győzelem"

    if "hazai" in t or "otthon" in t or "home" in t:
        return "Hazai győzelem"

    if "draw" in t and "no bet" not in t:
        return "Döntetlen"

    # fallback: inkább hazai
    return "Hazai győzelem"


def _build_model_input(matches: List[Dict[str, Any]]) -> str:
    """
    A meccsekből készít egy kompakt JSON-t, amit az AI kap.
    """
    compact_matches: List[Dict[str, Any]] = []

    for m in matches:
        fixture_id = (
            m.get("fixture_id")
            or m.get("id")
            or (m.get("fixture") or {}).get("id")
        )

        league_name = (
            m.get("league_name")
            or (m.get("league") or {}).get("name")
            or ""
        )

        country = (
            m.get("country")
            or (m.get("league") or {}).get("country")
            or ""
        )

        home_team = (
            m.get("home_team")
            or (m.get("teams") or {}).get("home", {}).get("name")
            or m.get("home")
            or ""
        )
        away_team = (
            m.get("away_team")
            or (m.get("teams") or {}).get("away", {}).get("name")
            or m.get("away")
            or ""
        )

        kickoff = (
            m.get("kickoff_local")
            or m.get("kickoff")
            or (m.get("fixture") or {}).get("date")
            or m.get("datetime")
            or m.get("date")
            or ""
        )

        odds_home = _safe_float(
            m.get("odds_home")
            or (m.get("odds") or {}).get("home")
        )
        odds_draw = _safe_float(
            m.get("odds_draw")
            or (m.get("odds") or {}).get("draw")
        )
        odds_away = _safe_float(
            m.get("odds_away")
            or (m.get("odds") or {}).get("away")
        )

        compact_matches.append(
            {
                "fixture_id": fixture_id,
                "league_name": league_name,
                "country": country,
                "home_team": home_team,
                "away_team": away_team,
                "kickoff": kickoff,
                "odds_home": odds_home or None,
                "odds_draw": odds_draw or None,
                "odds_away": odds_away or None,
                "extra": {
                    k: v
                    for k, v in m.items()
                    if k
                    not in {
                        "fixture_id",
                        "league_name",
                        "country",
                        "home_team",
                        "away_team",
                        "kickoff",
                        "odds_home",
                        "odds_draw",
                        "odds_away",
                    }
                },
            }
        )

    return json.dumps(compact_matches, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------
# OpenAI hívás
# ---------------------------------------------------------------------


def _call_openai_for_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Meghívja az OpenAI-t, és elvár egy szigorú JSON választ:
    {
      "tips": [
        {
          "fixture_id": 123,
          "tip_text": "...",
          "odds": 1.75,
          "confidence": 1-5,
          "risk_level": "alacsony"|"közepes"|"magas",
          "reason_hu": "...",
          "is_vip_candidate": true/false
        }, ...
      ]
    }
    """
    if not matches:
        return {"tips": []}

    system_prompt = (
        "Te vagy a SZELVÉNYKIRÁLY futball tippadó AI-ja.\n"
        "Feladatod, hogy a megadott meccsekre VALÓSÁGOSAN átgondolt, "
        "fegyelmezett 1X2 tippeket adj.\n\n"
        "Nagyon fontos, kőbe vésett szabályok:\n"
        "1) CSAK 1X2 piacot használhatsz.\n"
        "   Engedélyezett tippek:\n"
        "     - 'Hazai győzelem'\n"
        "     - 'Döntetlen'\n"
        "     - 'Vendég győzelem'\n"
        "   Minden más piac TILTOTT: over/under gól, 2.5 gól felett/alatt,\n"
        "   mindkét csapat szerez gólt, BTTS, gólszám, gólpiac, 1X, X2, 12,\n"
        "   'hazai vagy döntetlen', 'döntetlen vagy vendég', 'dupla esély',\n"
        "   'draw no bet', hendikep, ázsiai hendikep stb.\n\n"
        "2) Ha bizonytalan vagy, inkább NE adj tippet arra a meccsre.\n"
        "   Confidence skála 1–5: csak 3–5 közötti tippeket add vissza.\n\n"
        "3) Ligaprioritás (soft szabály):\n"
        "   - Előnyben részesítsd a nagyobb, ismertebb ligákat, főleg:\n"
        "       * top európai ligák (Premier League, La Liga, Serie A, Bundesliga, Ligue 1)\n"
        "       * erős első osztályok, európai kupák\n"
        "       * válogatott tornák\n"
        "   - U19/U23, barátságos és egzotikus ligák csak akkor, ha nagyon erős edge-et látsz.\n"
        "     Ha nem vagy biztos, írj NO BET-et (és azokat ne add vissza a listában).\n\n"
        "4) A legjobb 3 tippet tekintsd 'A-kategóriásnak' (magas bizalom, reális odds),\n"
        "   ezen felül max. 2–3 'B-kategóriás' tippet válassz.\n"
        "   Inkább legyen kevesebb, de erősebb tipp, mint több, gyenge.\n\n"
        "5) A válaszod SZIGORÚAN VALID JSON legyen, komment és extra szöveg nélkül.\n"
        '   Formátum:\n'
        '   {\n'
        '     "tips": [\n'
        "       {\n"
        '         "fixture_id": <int>,\n'
        '         "tip_text": "Hazai győzelem" / "Döntetlen" / "Vendég győzelem",\n'
        '         "odds": <float vagy null>,\n'
        '         "confidence": <1-5 egész>,\n'
        '         "risk_level": "alacsony" | "közepes" | "magas",\n'
        '         "reason_hu": "rövid magyar indoklás",\n'
        '         "is_vip_candidate": true vagy false\n'
        "       }, ...\n"
        "     ]\n"
        "   }\n"
    )

    user_content = (
        "Itt vannak a mai meccsek kompakt JSON formában. "
        "Elemezd őket, és add vissza a legjobb 1X2 tippeket a fenti formátumban.\n\n"
        "MECCSEK:\n"
        + _build_model_input(matches)
    )

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.4,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    content = resp.choices[0].message.content or ""
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("JSON root is not object")
    except Exception:
        return {"tips": []}

    if "tips" not in data or not isinstance(data["tips"], list):
        data["tips"] = []

    return data


# ---------------------------------------------------------------------
# Tipp kiválasztás, VIP / FREE csoportosítás
# ---------------------------------------------------------------------


def _classify_bet_strength(b: Dict[str, Any]) -> None:
    """
    A tipphez hozzárak:
      - league_priority
      - is_strong (A-kategória)
      - quality_score (VIP rendezéshez)
    """
    league_p = _league_priority(b.get("league_name") or "")
    conf = b.get("confidence", 0)
    odds = b.get("odds") or 0.0

    b["league_priority"] = league_p

    # Erős tipp feltételei:
    # - jó liga (priority <= 3)
    # - confidence >= 4
    # - odds kb. 1.35–2.30 között, vagy nincs odds, de nagyon erős jel
    is_strong = False
    if conf >= 4:
        if odds == 0.0:
            is_strong = league_p <= 3
        else:
            if 1.35 <= odds <= 2.30 and league_p <= 3:
                is_strong = True

    b["is_strong"] = is_strong

    # Minőség pontszám VIP rendezéshez (kisebb = jobb)
    # confidence lefelé rendezve, liga_priority, odds távolság egy „ideális” 1.80-tól
    ideal_odds = 1.8
    if odds <= 1.01:
        odds_penalty = 0.8
    else:
        odds_penalty = abs(odds - ideal_odds) / 1.8

    b["quality_score"] = (
        league_p * 1.0
        - conf * 0.7
        + odds_penalty
    )


def _build_bets_from_ai(
    matches: List[Dict[str, Any]], ai_data: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    AI válaszából (tips) épít public_bets és vip_bets listát.
    """
    # fixture_id -> raw match
    match_by_id: Dict[Any, Dict[str, Any]] = {}
    for m in matches:
        fid = (
            m.get("fixture_id")
            or m.get("id")
            or (m.get("fixture") or {}).get("id")
        )
        if fid is not None:
            match_by_id[str(fid)] = m

    tips = ai_data.get("tips") or []
    cleaned: List[Dict[str, Any]] = []

    for t in tips:
        fixture_id = t.get("fixture_id")
        if fixture_id is None:
            continue

        raw_tip = str(t.get("tip_text") or "").strip()
        if not raw_tip:
            continue

        # Tiltott piac?
        if _is_forbidden_market(raw_tip):
            continue

        tip_text = _normalize_1x2_tip(raw_tip)
        odds = _safe_float(t.get("odds"), 0.0)
        confidence = int(round(_safe_float(t.get("confidence"), 0.0)))

        # Gyenge tipp -> dobjuk
        if confidence < 3:
            continue

        risk_level = (t.get("risk_level") or "közepes").lower()
        if risk_level not in {"alacsony", "közepes", "magas"}:
            risk_level = "közepes"

        reason_hu = t.get("reason_hu") or "Az adatok alapján ez tűnik a legvalószínűbb kimenetelnek."
        is_vip_candidate = bool(t.get("is_vip_candidate", True))

        m = match_by_id.get(str(fixture_id), {})
        league_name = (
            m.get("league_name")
            or (m.get("league") or {}).get("name")
            or ""
        )
        country = (
            m.get("country")
            or (m.get("league") or {}).get("country")
            or ""
        )
        home_team = (
            m.get("home_team")
            or (m.get("teams") or {}).get("home", {}).get("name")
            or m.get("home")
            or ""
        )
        away_team = (
            m.get("away_team")
            or (m.get("teams") or {}).get("away", {}).get("name")
            or m.get("away")
            or ""
        )
        kickoff = (
            m.get("kickoff_local")
            or m.get("kickoff")
            or (m.get("fixture") or {}).get("date")
            or m.get("datetime")
            or m.get("date")
            or ""
        )

        match_title = (
            f"{home_team} vs {away_team} ({league_name}, {kickoff})"
            if kickoff
            else f"{home_team} vs {away_team} ({league_name})"
        )

        bet = {
            "fixture_id": fixture_id,
            "match": match_title,
            "tip": tip_text,
            "odds": odds if odds > 1.01 else None,
            "confidence": confidence,
            "risk_level": risk_level,
            "reason": reason_hu,
            "league_name": league_name,
            "country": country,
            "home_team": home_team,
            "away_team": away_team,
            "kickoff": kickoff,
            "is_vip_candidate": is_vip_candidate,
        }

        _classify_bet_strength(bet)

        # Exotikus liga + bizonytalan -> dobjuk (ne kerüljön be sehová)
        if bet["league_priority"] >= 5 and bet["confidence"] < 4:
            continue

        cleaned.append(bet)

    # Ha az AI válasz használhatatlan, legyen primitív fallback
    if not cleaned:
        fallback_bets: List[Dict[str, Any]] = []
        for m in matches:
            fid = (
                m.get("fixture_id")
                or m.get("id")
                or (m.get("fixture") or {}).get("id")
            )
            if fid is None:
                continue

            league_name = (
                m.get("league_name")
                or (m.get("league") or {}).get("name")
                or ""
            )
            home_team = (
                m.get("home_team")
                or (m.get("teams") or {}).get("home", {}).get("name")
                or m.get("home")
                or ""
            )
            away_team = (
                m.get("away_team")
                or (m.get("teams") or {}).get("away", {}).get("name")
                or m.get("away")
                or ""
            )
            kickoff = (
                m.get("kickoff_local")
                or m.get("kickoff")
                or (m.get("fixture") or {}).get("date")
                or m.get("datetime")
                or m.get("date")
                or ""
            )

            match_title = (
                f"{home_team} vs {away_team} ({league_name}, {kickoff})"
                if kickoff
                else f"{home_team} vs {away_team} ({league_name})"
            )

            bet = {
                "fixture_id": fid,
                "match": match_title,
                "tip": "Hazai győzelem",
                "odds": None,
                "confidence": 3,
                "risk_level": "közepes",
                "reason": "Egyszerű fallback tipp: hazai előnyt feltételezve.",
                "league_name": league_name,
                "country": "",
                "home_team": home_team,
                "away_team": away_team,
                "kickoff": kickoff,
                "is_vip_candidate": True,
            }
            _classify_bet_strength(bet)
            fallback_bets.append(bet)

        cleaned = fallback_bets

    # VIP / PUBLIC kiválasztás

    # A-kategóriás (erős) jelöltek
    strong_candidates = [b for b in cleaned if b["is_strong"] and b.get("is_vip_candidate", True)]
    strong_sorted = sorted(strong_candidates, key=lambda x: x["quality_score"])

    vip_bets: List[Dict[str, Any]] = []

    # 1) erős, kiemelt tippek – max 3
    for b in strong_sorted:
        if len(vip_bets) >= 3:
            break
        vip_bets.append(b)

    # 2) B-kategóriás tippek (max 2–3, összesen max 6 VIP)
    other_candidates = [
        b for b in cleaned
        if b not in vip_bets and b.get("is_vip_candidate", True)
    ]
    other_sorted = sorted(other_candidates, key=lambda x: x["quality_score"])

    for b in other_sorted:
        if len(vip_bets) >= 6:
            break
        # gyenge odds / nagyon magas kockázat esetén hagyjuk ki
        odds = b.get("odds") or 0.0
        if odds != 0.0 and odds > 3.2:
            continue
        vip_bets.append(b)

    # 3) Public: a maradék közül 3–5 könnyebb tipp
    public_bets: List[Dict[str, Any]] = []
    remaining_for_public = [b for b in cleaned if b not in vip_bets]
    public_sorted = sorted(
        remaining_for_public,
        key=lambda x: (x["league_priority"], -x["confidence"], x.get("odds") or 2.0),
    )

    for b in public_sorted:
        if len(public_bets) >= 5:
            break
        public_bets.append(b)

    # Ha valamiért nincs public bet, de vannak VIP-ek, vegyünk át 2–3-t
    if not public_bets and vip_bets:
        public_bets = vip_bets[:3]

    return public_bets, vip_bets


# ---------------------------------------------------------------------
# Telegram szövegek
# ---------------------------------------------------------------------


def _build_public_telegram_text(bets: List[Dict[str, Any]]) -> str:
    import datetime as _dt

    today = _dt.date.today().strftime("%Y.%m.%d.")
    lines: List[str] = []
    lines.append("🎟 SZELVÉNYKIRÁLY – FREE TIPPEK MA")
    lines.append(f"Dátum: {today}\n")

    if not bets:
        lines.append("Ma nem találtam igazán erős FREE tippet. Inkább várjunk jobb lehetőségekre. 👀")
        return "\n".join(lines)

    lines.append("Ezek a mai, óvatosabb FREE tippek:\n")

    for idx, b in enumerate(bets, start=1):
        odds_str = f"{b['odds']:.2f}" if b.get("odds") else "n/a"
        lines.append(
            f"{idx}. {b.get('match')}\n"
            f"🎯 Tipp: {b.get('tip')}\n"
            f"📉 Odd: {odds_str}\n"
        )

    lines.append("⚠️ Felelős játék: soha ne tégy fel olyan összeget, amit nem engedhetsz meg magadnak elveszíteni.")
    return "\n".join(lines)


def _build_vip_telegram_text(bets: List[Dict[str, Any]]) -> str:
    import datetime as _dt

    today = _dt.date.today().strftime("%Y.%m.%d.")
    lines: List[str] = []
    lines.append("🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI MA ESTÉRE 🔥")
    lines.append(f"Dátum: {today}\n")

    if not bets:
        lines.append("Ma nem találtam elég megbízható VIP tippet. Inkább nem erőltetem – a tőke megőrzése az első. 💰")
        return "\n".join(lines)

    lines.append(f"Tippek száma: {len(bets)} (cél: 3 erős + max. 2–3 kiegészítő tipp)")
    lines.append("────────────────────────────\n")

    if len(bets) < 5:
        lines.append("Ma inkább MINŐSÉG, mint mennyiség: kevesebb, de erősebb tippet küldök.\n")
    else:
        lines.append("Ezek a meccsek kombinálva egy erős, de még ésszerűen vállalható VIP szelvényt adnak:\n")

    # Kiemelt tippek: a VIP listán belül quality_score szerint legjobb 3
    sorted_vip = sorted(bets, key=lambda x: x["quality_score"])
    highlighted = sorted_vip[:3]
    highlighted_ids = {id(b) for b in highlighted}

    for idx, b in enumerate(bets, start=1):
        is_highlight = id(b) in highlighted_ids
        prefix = "💎 KIEMELT – " if is_highlight else ""
        odds_str = f"{b['odds']:.2f}" if b.get("odds") else "n/a"
        conf = b.get("confidence", 3)
        risk = b.get("risk_level", "közepes")
        reason = b.get("reason") or "Az adatok alapján ez tűnik a legvalószínűbbnek."
        fixture_id = b.get("fixture_id")

        stars = "⭐" * max(1, min(conf, 5))

        if risk == "alacsony":
            risk_emoji = "🟢"
        elif risk == "magas":
            risk_emoji = "🔴"
        else:
            risk_emoji = "🟠"

        lines.append(
            f"{idx}. {prefix}{b.get('match')}\n"
            f"🎯 Tipp: {b.get('tip')}\n"
            f"📉 Odd: {odds_str}\n"
            f"⚠️ Kockázat: {risk_emoji} {risk}\n"
            f"⭐ Bizalom: {stars} ({conf}/5)\n"
            f"🧠 Miért? {reason}\n"
            f"[ID={fixture_id}]\n"
        )

    # 3 kiemelt kombi – 2 000 Ft példa tét
    highlight_with_odds = [b for b in highlighted if b.get("odds")]
    if len(highlight_with_odds) >= 2:
        total_odds = 1.0
        for b in highlight_with_odds:
            total_odds *= float(b["odds"])
        stake = 2000.0
        potential = stake * total_odds

        lines.append("────────────────────────────")
        lines.append("📌 Kiemelt kombi példa (nem kötelező követni):")
        lines.append(
            f"Ha a 3 kiemelt meccset 2 000 Ft-tal egy kombiban játszod meg,\n"
            f"az összodds kb. {total_odds:.2f}, a várható bruttó nyeremény pedig ~{_format_huf(potential)}."
        )

    lines.append("\n⚠️ Felelős játék: a VIP tippek sem garantáltak, kezeld őket hosszú távú stratégiaként.")
    return "\n".join(lines)


# ---------------------------------------------------------------------
# FŐ FÜGGVÉNY – ezt hívja a main.py
# ---------------------------------------------------------------------


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fő belépési pont a main.py számára.

    Bemenet: matches – a bot.matches.fetch_matches_for_today() eredménye.
    Kimenet:
      {
        "public_bets": [...],
        "vip_bets": [...],
        "telegram_public_text": "...",
        "telegram_vip_text": "..."
      }
    """
    ai_data = _call_openai_for_tips(matches)
    public_bets, vip_bets = _build_bets_from_ai(matches, ai_data)

    public_text = _build_public_telegram_text(public_bets)
    vip_text = _build_vip_telegram_text(vip_bets)

    return {
        "public_bets": public_bets,
        "vip_bets": vip_bets,
        "telegram_public_text": public_text,
        "telegram_vip_text": vip_text,
    }
