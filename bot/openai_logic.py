import os
import json
import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import random

from openai import OpenAI


# ====== OPENAI KLIENS =========================================================

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ====== ADATSTRUKTÚRÁK ========================================================


@dataclass
class MatchInfo:
    fixture_id: str
    league_name: str
    country: str
    kickoff_str: str
    home_team: str
    away_team: str
    raw: Dict[str, Any]


@dataclass
class TipResult:
    fixture_id: str
    match: str
    tip: str
    confidence: float
    risk_level: str
    is_highlighted: bool
    reason: str
    odds: Optional[float]


# ====== SEGÉDFÜGGVÉNYEK – MECCS ADATOK KINYERÉSE ==============================


def _safe_get(d: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Próbál több kulcsot is, az első nem-None értéket adja vissza."""
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return None


def _build_match_info(m: Dict[str, Any]) -> Optional[MatchInfo]:
    """
    Rugalmassan próbáljuk összerakni a meccs adatait,
    hogy működjön akkor is, ha a sport API struktúrája változik.
    """

    # --- fixture_id ---
    fixture_id = (
        _safe_get(m, "fixture_id", "id", "fixtureId")
        or _safe_get(m.get("fixture", {}), "id")
        or _safe_get(m.get("match", {}), "id")
    )
    if fixture_id is None:
        # ha tényleg semmi, akkor generálunk valami stabil-ish stringet
        fixture_id = str(m.get("id") or m.get("fixture_id") or m.get("match_id") or random.randint(10_000, 99_999))
    fixture_id = str(fixture_id)

    # --- league / country ---
    league = _safe_get(m, "league_name", "league", "competition", "tournament") or ""
    if isinstance(league, dict):
        league_name = str(_safe_get(league, "name", "league_name") or "")
        country = str(_safe_get(league, "country", "cc") or "")
    else:
        league_name = str(league)
        country = str(_safe_get(m, "country", "country_name") or "")

    # --- teams ---
    home_team = ""
    away_team = ""

    teams = _safe_get(m, "teams", "participants")
    if isinstance(teams, dict):
        home_team = str(_safe_get(teams.get("home", {}), "name", "team_name") or "")
        away_team = str(_safe_get(teams.get("away", {}), "name", "team_name") or "")
    elif isinstance(teams, list) and len(teams) >= 2:
        home_team = str(_safe_get(teams[0], "name", "team_name") or "")
        away_team = str(_safe_get(teams[1], "name", "team_name") or "")

    # fallback, ha máshol vannak a nevek
    if not home_team:
        home_team = str(_safe_get(m, "home_team", "homeTeam", "home") or "")
    if not away_team:
        away_team = str(_safe_get(m, "away_team", "awayTeam", "away") or "")

    if not home_team or not away_team:
        # ha nincs tiszta csapatnév, ezt a meccset inkább kihagyjuk
        return None

    # --- kickoff idő (stringként, recap-formázáshoz) ---
    kickoff = (
        _safe_get(m, "kickoff_local", "kickoff", "datetime", "date", "start_time", "startTime")
        or _safe_get(m.get("fixture", {}), "date")
    )

    kickoff_str = ""
    if isinstance(kickoff, datetime.datetime):
        kickoff_str = kickoff.isoformat()
    elif isinstance(kickoff, str):
        kickoff_str = kickoff
    else:
        # ha semmi használható, legalább dátum: ma
        kickoff_str = datetime.datetime.now().isoformat(timespec="minutes")

    return MatchInfo(
        fixture_id=fixture_id,
        league_name=league_name.strip() or "Ismeretlen liga",
        country=country.strip() or "World",
        kickoff_str=kickoff_str,
        home_team=home_team,
        away_team=away_team,
        raw=m,
    )


def _serialize_match_for_llm(mi: MatchInfo) -> Dict[str, Any]:
    """Kis, LLM-barát struktúra minden meccshez."""
    return {
        "fixture_id": mi.fixture_id,
        "league": mi.league_name,
        "country": mi.country,
        "kickoff": mi.kickoff_str,
        "home_team": mi.home_team,
        "away_team": mi.away_team,
        # ha később akarunk még statokat átadni, itt bővíthetjük
    }


# ====== TELEGRAM SZÖVEG GENERÁLÁS ============================================


def _risk_emoji(risk: str) -> str:
    r = risk.lower()
    if "alacsony" in r:
        return "🟢 alacsony"
    if "magas" in r:
        return "🔴 magas"
    return "🟠 közepes"


def _stars(conf: float) -> str:
    """
    0–5 közötti confidence -> csillagok.
    pl. 4.2 -> ⭐⭐⭐⭐☆ (4/5)
    """
    conf = max(0.0, min(5.0, conf))
    full = int(round(conf))
    full = max(0, min(5, full))
    return "⭐" * full + "☆" * (5 - full) + f" ({full}/5)"


def _format_match_line(idx: int, tip: TipResult, vip: bool) -> str:
    match_header = f"{idx}. {'💎 KIEMELT – ' if (vip and tip.is_highlighted) else ''}{tip.match}"
    lines = [
        match_header,
        f"🎫 Tipp: {tip.tip}",
    ]

    if tip.odds is not None:
        lines.append(f"📊 Odds (1X2): {tip.odds:.2f}")
    else:
        lines.append("📊 Odds (1X2): n/a")

    lines.append(f"⚠️ Kockázat: {_risk_emoji(tip.risk_level)}")
    lines.append(f"💡 Bizalom: {_stars(tip.confidence)}")
    if tip.reason:
        lines.append(f"🧠 Miért? {tip.reason}")

    return "\n".join(lines)


def _build_vip_telegram_text(tips: List[TipResult], slot_label: str) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    if not tips:
        return (
            f"🔥 SZELVÉNYKIRÁLY VIP – {slot_label} 🔥\n"
            f"Dátum: {today}\n\n"
            "Ma sajnos nem sikerült elég erős VIP tippet találni. "
            "Inkább kihagyjuk, mint hogy erőltetett, gyenge értékű szelvényt adjunk. 🙏"
        )

    lines: List[str] = []
    lines.append(f"🔥 SZELVÉNYKIRÁLY VIP – {slot_label} 🔥")
    lines.append(f"Dátum: {today}")
    lines.append(f"Tippjeink száma: {len(tips)}")
    lines.append("────────────────────────────")

    lines.append(
        "Ezek a meccsek kombinálva egy erős, de még ésszerűen vállalható kockázatú VIP "
        "szelvényt adnak. Mindig tartsd be a bankroll menedzsmentet!"
    )
    lines.append("")

    # Kiemeltek előre rendezve
    sorted_tips = sorted(tips, key=lambda t: (not t.is_highlighted, -t.confidence))

    for idx, tip in enumerate(sorted_tips, start=1):
        lines.append(_format_match_line(idx, tip, vip=True))
        lines.append("")  # üres sor

    return "\n".join(lines).strip()


def _build_free_telegram_text(tips: List[TipResult], slot_label: str) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    if not tips:
        return (
            f"👑 SZELVÉNYKIRÁLY FREE – {slot_label}\n"
            f"Dátum: {today}\n\n"
            "Ma sajnos nem találtunk olyan biztonságos FREE tippet, amit jó szívvel küldenénk ki. "
            "Inkább kihagyjuk, mint hogy erőltessük. 🙏"
        )

    lines: List[str] = []
    lines.append(f"👑 SZELVÉNYKIRÁLY FREE – {slot_label}")
    lines.append(f"Dátum: {today}")
    lines.append(f"Tippjeink száma: {len(tips)}")
    lines.append("")
    lines.append("Ezek a mai, óvatosabb FREE tippek:")
    lines.append("")

    for idx, tip in enumerate(tips, start=1):
        lines.append(_format_match_line(idx, tip, vip=False))
        lines.append("")

    lines.append(
        "⚠️ Felelős játék: soha ne tegyél fel olyan összeget, amit nem engedhetsz meg magadnak elveszíteni."
    )

    return "\n".join(lines).strip()


# ====== OPENAI HÍVÁS – ITT ENGEDEDJÜK SZABADON AZ AI-T ========================


def _call_openai_for_tips(matches: List[MatchInfo]) -> Optional[Dict[str, Any]]:
    """
    Meccslista -> OpenAI JSON válasz.
    Itt mondjuk meg az LLM-nek, hogy szabadon döntsön: Hazai / Döntetlen / Vendég.
    Csak 1X2 piac, semmi 1X, X2, gólok, BTTS stb.
    """

    if not matches:
        return None

    matches_payload = [_serialize_match_for_llm(mi) for mi in matches]

    system_msg = (
        "Te egy profi sportfogadási elemző AI vagy, aki futballmeccsekre ad tippeket.\n"
        "Fontos szabályok:\n"
        "- CSAK 1X2 piacot használsz: 'Hazai győzelem', 'Döntetlen' vagy 'Vendég győzelem'.\n"
        "- TILOS bármilyen kombináció: 1X, X2, 12, hendikep, over/under gólok, BTTS stb.\n"
        "- A döntéseidet statisztikai, forma-, keret- és motivációs szempontok alapján hozd meg.\n"
        "- Inkasz inkább kevesebb tippet, de azok legyenek minőségibbek.\n"
        "- Részesítsd előnyben az ismertebb ligákat (top európai ligák, nagyobb 1. osztályok, válogatott tornák).\n"
        "- Exotikus ligát csak akkor válassz, ha egyértelműnek érzed az erőviszonyokat.\n"
    )

    user_msg = {
        "role": "user",
        "content": (
            "Itt egy meccslista JSON-ben. Elemezd őket, és adj vissza tippeket az alábbi szigorú JSON formában.\n\n"
            "Kérések:\n"
            "- Adj 3–7 VIP tippet, ezek közül pontosan 3 legyen 'kiemelt'.\n"
            "- Adj 2–5 óvatosabb FREE tippet.\n"
            "- Minden tipphez add meg:\n"
            "  * fixture_id (az eredeti mezőből)\n"
            "  * match (szép szöveg: 'CsapatA vs CsapatB (Liga, időpont)')\n"
            "  * tip (csak: 'Hazai győzelem', 'Döntetlen' vagy 'Vendég győzelem')\n"
            "  * risk_level ('alacsony', 'közepes' vagy 'magas')\n"
            "  * confidence (0.0–5.0 skálán)\n"
            "  * is_highlighted (bool, csak VIP-ben használjuk)\n"
            "  * reason (1–2 mondat, rövid magyarázat magyarul)\n"
            "  * odds (ha tudsz becslést adni 1X2 oddsról, pl. 1.75; ha nem, legyen null)\n\n"
            "A KIMENET PONTOSAN EZ A JSON legyen (idézőjelek, kulcsnevek stb.):\n"
            "{\n"
            '  \"vip_tips\": [ { ... } ],\n'
            '  \"free_tips\": [ { ... } ]\n"
            "}\n\n"
            f"Meccslista JSON-ben:\n{json.dumps(matches_payload, ensure_ascii=False)}"
        ),
    }

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.65,
            messages=[
                {"role": "system", "content": system_msg},
                user_msg,
            ],
        )
    except Exception as e:
        print("OpenAI hívás hiba:", repr(e))
        return None

    try:
        content = resp.choices[0].message.content or ""
        data = json.loads(content)
        return data
    except Exception as e:
        print("OpenAI JSON parse hiba:", repr(e))
        print("Válasz tartalom:", resp.choices[0].message.content)
        return None


# ====== FALLBACK – HA OPENAI NEM MŰKÖDIK =====================================


def _fallback_simple_tips(matches: List[MatchInfo]) -> Dict[str, Any]:
    """
    Ha OpenAI nem válaszol, egy nagyon egyszerű tartalék logika:
    - véletlenül kiválaszt 3–5 meccset,
    - mindegyikre hazai / vendég / döntetlen véletlenszerűen,
    hogy legalább menjen a bot, ne álljon le.
    Nem szép, de jobb, mint a semmi.
    """
    if not matches:
        return {"vip_tips": [], "free_tips": []}

    picks = random.sample(matches, k=min(5, len(matches)))

    outcomes = ["Hazai győzelem", "Döntetlen", "Vendég győzelem"]
    tips: List[TipResult] = []

    for mi in picks:
        tip_text = random.choice(outcomes)
        tip = TipResult(
            fixture_id=mi.fixture_id,
            match=f"{mi.home_team} vs {mi.away_team} ({mi.league_name}, {mi.kickoff_str}) [ID={mi.fixture_id}]",
            tip=tip_text,
            confidence=3.0,
            risk_level="közepes",
            is_highlighted=False,
            reason="Egyszerű tartalék tipp – az OpenAI értékelés most nem elérhető.",
            odds=None,
        )
        tips.append(tip)

    # első 3 VIP, maradék FREE
    vip = tips[:3]
    free = tips[3:]

    return {
        "vip_tips": [t.__dict__ for t in vip],
        "free_tips": [t.__dict__ for t in free],
    }


# ====== FŐ FÜGGVÉNY – EZT HÍVJA A main.py ====================================


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    A main.py innen kér:
      - Telegram szövegeket (FREE + VIP),
      - recap számára JSON-okat (public_bets, vip_bets).
    """

    match_infos: List[MatchInfo] = []
    for m in matches:
        mi = _build_match_info(m)
        if mi:
            match_infos.append(mi)

    if not match_infos:
        print("Nincs olyan meccs, amit értelmesen fel tudnánk dolgozni.")
        slot_label = "NAPI TIPPEK"
        return {
            "telegram_public_text": _build_free_telegram_text([], slot_label),
            "telegram_vip_text": _build_vip_telegram_text([], slot_label),
            "public_bets": [],
            "vip_bets": [],
        }

    # OpenAI hívás
    data = _call_openai_for_tips(match_infos)
    if data is None:
        print("OpenAI eredmény nincs, fallback logika lép életbe.")
        data = _fallback_simple_tips(match_infos)

    vip_raw = data.get("vip_tips") or []
    free_raw = data.get("free_tips") or []

    vip_tips: List[TipResult] = []
    free_tips: List[TipResult] = []

    def _parse_tip(obj: Dict[str, Any], is_vip: bool) -> Optional[TipResult]:
        try:
            fixture_id = str(obj.get("fixture_id") or obj.get("id") or "")
            match = str(obj.get("match") or "")
            tip = str(obj.get("tip") or "")
            risk_level = str(obj.get("risk_level") or "közepes")
            confidence = float(obj.get("confidence") or 3.0)
            is_highlighted = bool(obj.get("is_highlighted") and is_vip)
            reason = str(obj.get("reason") or "")
            odds_val = obj.get("odds")
            odds = float(odds_val) if odds_val not in (None, "", "null") else None

            # biztonság kedvéért: csak 3 féle tippet engedünk át
            if tip not in ("Hazai győzelem", "Döntetlen", "Vendég győzelem"):
                return None

            return TipResult(
                fixture_id=fixture_id,
                match=match,
                tip=tip,
                confidence=confidence,
                risk_level=risk_level,
                is_highlighted=is_highlighted,
                reason=reason,
                odds=odds,
            )
        except Exception as e:
            print("Tip parse hiba:", repr(e), "obj=", obj)
            return None

    for obj in vip_raw:
        tr = _parse_tip(obj, is_vip=True)
        if tr:
            vip_tips.append(tr)

    for obj in free_raw:
        tr = _parse_tip(obj, is_vip=False)
        if tr:
            free_tips.append(tr)

    # ha az AI valamiért keveset adott, egy kicsit rásegítünk (nem kötelező)
    if not vip_tips and free_tips:
        # swap: ha csak free van, azokból emelünk át VIP-be
        vip_tips = free_tips[:3]
        free_tips = free_tips[3:]

    slot_label = "NAPI TIPPEK"

    vip_text = _build_vip_telegram_text(vip_tips, slot_label)
    free_text = _build_free_telegram_text(free_tips, slot_label)

    # recap-hez elég egy egyszerűbb struktúra
    vip_bets = [
        {
            "fixture_id": t.fixture_id,
            "match": t.match,
            "tip": t.tip,
        }
        for t in vip_tips
    ]

    public_bets = [
        {
            "fixture_id": t.fixture_id,
            "match": t.match,
            "tip": t.tip,
        }
        for t in free_tips
    ]

    return {
        "telegram_public_text": free_text,
        "telegram_vip_text": vip_text,
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
