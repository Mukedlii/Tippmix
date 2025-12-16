import os
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# =============== OPENAI KLIENS =====================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


# =============== ADATSTRUKTÚRÁK =====================

@dataclass
class Match:
    fixture_id: Optional[int]
    home_team: str
    away_team: str
    league: str
    country: str
    kickoff: str  # szövegként (helyi idő, pl. "2025-12-16 14:00")
    odds_home: Optional[float] = None
    odds_draw: Optional[float] = None
    odds_away: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Match":
        return cls(
            fixture_id=data.get("fixture_id") or data.get("id"),
            home_team=data.get("home_team") or data.get("home") or "Ismeretlen hazai",
            away_team=data.get("away_team") or data.get("away") or "Ismeretlen vendég",
            league=data.get("league_name") or data.get("league") or "Ismeretlen liga",
            country=data.get("country") or data.get("country_name") or "",
            kickoff=str(
                data.get("kickoff_local")
                or data.get("kickoff")
                or data.get("datetime")
                or data.get("date")
                or ""
            ),
            odds_home=_safe_float(data.get("odds_home")),
            odds_draw=_safe_float(data.get("odds_draw")),
            odds_away=_safe_float(data.get("odds_away")),
        )


@dataclass
class AiTip:
    match: Match
    pick: str          # "home" | "away" | "draw"
    confidence: int    # 1–5
    risk: str          # "low" | "medium" | "high"
    reason: str
    vip_candidate: bool


# =============== SEGÉDFÜGGVÉNYEK =====================


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


_TOP_LEAGUE_KEYWORDS = [
    "premier league",
    "la liga",
    "serie a",
    "bundesliga",
    "ligue 1",
    "champions league",
    "europa league",
    "conference league",
]

_MAJOR_LEAGUE_KEYWORDS = [
    "first division",
    "1. liga",
    "1. league",
    "super league",
    "eredivisie",
    "primeira liga",
    "championship",
    "bundesliga 2",
    "liga i",
    "liga pro",
    "otp bank liga",
    "nb i",
]

_YOUTH_OR_FRIENDLY_KEYWORDS = [
    "u19",
    "u20",
    "u21",
    "u22",
    "u23",
    "youth",
    "friendly",
    "friendlies",
]


def _classify_league(league: str) -> str:
    """Visszaad: 'top', 'major', 'youth_or_friendly', 'other'."""
    name = (league or "").lower()
    for kw in _TOP_LEAGUE_KEYWORDS:
        if kw in name:
            return "top"
    for kw in _MAJOR_LEAGUE_KEYWORDS:
        if kw in name:
            return "major"
    for kw in _YOUTH_OR_FRIENDLY_KEYWORDS:
        if kw in name:
            return "youth_or_friendly"
    return "other"


def _league_score_bonus(league: str) -> int:
    cat = _classify_league(league)
    if cat == "top":
        return 30
    if cat == "major":
        return 18
    if cat == "youth_or_friendly":
        return -5
    return 5


def _normalize_pick(raw_pick: Any) -> Optional[str]:
    """
    Az AI pick mezőjét normalizálja.
    Csak 'home' / 'away' / 'draw' elfogadott. Ha mást kapunk -> None.
    NINCS default hazai.
    """
    if not raw_pick:
        return None
    t = str(raw_pick).strip().lower()

    if t in {"home", "hazai", "1"}:
        return "home"
    if t in {"away", "vendég", "vendeg", "2"}:
        return "away"
    if t in {"draw", "döntetlen", "dontetlen", "x"}:
        return "draw"
    return None


def _normalize_risk(raw_risk: Any) -> str:
    t = (str(raw_risk) or "").strip().lower()
    if t in {"low", "alacsony"}:
        return "low"
    if t in {"high", "magas", "kockázatos"}:
        return "high"
    return "medium"


def _safe_confidence(x: Any) -> int:
    try:
        v = int(x)
    except Exception:
        return 3
    return max(1, min(5, v))


# =============== OPENAI HÍVÁS =====================


def _build_ai_prompt(matches: List[Match]) -> str:
    """
    Részletes, magyar prompt. Figyelem:
      - csak 1X2 tippek,
      - ne automatikusan hazai,
      - max 7 VIP jelölt,
      - max 5 FREE jelölt,
      - preferált ligák: top + komoly 1. osztályok.
    """
    lines: List[str] = []
    lines.append(
        "Egy sportfogadási asszisztens vagy, aki mély statisztikai elemzés alapján "
        "ad 1X2 (hazai/döntetlen/vendég) focitippeket."
    )
    lines.append("")
    lines.append("Fontos szabályok:")
    lines.append("1. CSAK 1X2 piac: 'home' (hazai), 'draw' (döntetlen), 'away' (vendég).")
    lines.append(
        "2. NE válaszd automatikusan a hazai csapatot. Ha a vendég erősebb, "
        "nyugodtan legyen 'away', ha kiegyenlített, lehet 'draw' vagy 'skip'."
    )
    lines.append(
        "3. Előnyben részesíted a nagyobb ligákat: top európai bajnokságok, komoly "
        "1. osztályok, válogatott tornák. Exotikus / U19 / U23 / barátságos meccs "
        "csak akkor legyen tipp, ha nagyon egyértelmű statisztikai fölényt látsz."
    )
    lines.append(
        "4. Maximum 7 erősebb VIP jelölt tippet kérünk, minimum 3-at, ha van elég jó meccs."
    )
    lines.append(
        "5. Minden meccsnél adj meg egy 1–5 közötti bizalmi szintet (confidence) "
        "és egy 'low' / 'medium' / 'high' risk értéket."
    )
    lines.append(
        "6. Ha úgy érzed, hogy egy meccs túl bizonytalan vagy kaotikus, állítsd 'skip'=true-ra."
    )
    lines.append("")
    lines.append("A válaszod JSON lesz, a következő struktúrával:")
    lines.append(
        """
{
  "tips": [
    {
      "fixture_id": 12345,
      "pick": "home" | "draw" | "away",
      "confidence": 1-5,
      "risk": "low" | "medium" | "high",
      "reason_hu": "rövid magyar indoklás",
      "vip_candidate": true | false,
      "skip": false
    },
    ...
  ]
}
""".strip()
    )
    lines.append("")
    lines.append("Meccslista (elemzd, majd dönts, kell-e tipp rájuk):")

    for m in matches:
        lines.append(
            f"- fixture_id={m.fixture_id} | {m.country} – {m.league} | "
            f"{m.home_team} vs {m.away_team} | kickoff={m.kickoff} | "
            f"odds(1/x/2)={m.odds_home}/{m.odds_draw}/{m.odds_away}"
        )

    lines.append("")
    lines.append(
        "Adj vissza minél tisztább, jól formázott JSON-t, extra komment vagy szöveg nélkül."
    )

    return "\n".join(lines)


def _call_openai_for_tips(matches: List[Match]) -> Dict[str, Any]:
    """
    Meghívja az OpenAI Chat Completions API-t és visszaadja a nyers JSON-t (dict).
    Ha hiba van vagy nincs kliens, üres dictet ad vissza.
    """
    if client is None:
        print("Nincs OPENAI_API_KEY beállítva – AI tippek kihagyva.")
        return {}

    prompt = _build_ai_prompt(matches)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Te egy sportfogadási tipster asszisztens vagy.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print("OpenAI hívási hiba:", repr(e))
        return {}

    try:
        content = resp.choices[0].message.content
        data = json.loads(content)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as e:
        print("OpenAI JSON parse hiba:", repr(e))
        return {}


def _parse_ai_tips(matches: List[Match], raw: Dict[str, Any]) -> List[AiTip]:
    """
    Nyers JSON -> AiTip lista.
    Csak azokat vesszük fel, ahol:
      - pick ∈ {home,away,draw}
      - confidence >= 3
      - skip != true
    NINCS default hazai!
    """
    id_map: Dict[int, Match] = {}
    for m in matches:
        if m.fixture_id is not None:
            id_map[int(m.fixture_id)] = m

    tips: List[AiTip] = []
    raw_tips = raw.get("tips") or []
    if not isinstance(raw_tips, list):
        return tips

    for item in raw_tips:
        if not isinstance(item, dict):
            continue

        skip = bool(item.get("skip", False))
        if skip:
            continue

        fid = item.get("fixture_id")
        try:
            fid_int = int(fid)
        except Exception:
            continue

        match = id_map.get(fid_int)
        if not match:
            continue

        pick = _normalize_pick(item.get("pick"))
        if pick is None:
            # ismeretlen pick -> inkább hagyjuk ki, mint hogy hazait erőltessünk
            continue

        confidence = _safe_confidence(item.get("confidence"))
        if confidence < 3:
            # gyenge bizalmú tippet ne küldjünk ki
            continue

        risk = _normalize_risk(item.get("risk"))
        reason = item.get("reason_hu") or "Nincs részletes indoklás."
        vip_candidate = bool(item.get("vip_candidate", False))

        tips.append(
            AiTip(
                match=match,
                pick=pick,
                confidence=confidence,
                risk=risk,
                reason=reason,
                vip_candidate=vip_candidate,
            )
        )

    return tips


# =============== PONTOZÁS, LISTÁK =====================


def _score_tip(t: AiTip) -> int:
    """
    Összpontszám ligaszint + bizalom + kockázat alapján.
    Ezt használjuk VIP és kiemelt tippek sorrendezésére.
    """
    score = 0
    score += _league_score_bonus(t.match.league)
    score += t.confidence * 10
    if t.risk == "low":
        score += 5
    elif t.risk == "high":
        score -= 3
    return score


def _format_tip_line(idx: int, t: AiTip, kiemelt: bool = False) -> str:
    m = t.match
    fixture_part = f"{m.home_team} vs {m.away_team} ({m.league} {m.country}, {m.kickoff})"
    id_part = f"[ID={m.fixture_id}]" if m.fixture_id is not None else ""

    if t.pick == "home":
        tip_text = "Hazai győzelem"
    elif t.pick == "away":
        tip_text = "Vendég győzelem"
    else:
        tip_text = "Döntetlen"

    stars = "⭐" * t.confidence + "☆" * (5 - t.confidence)

    if t.risk == "low":
        risk_emoji = "🟢"
        risk_text = "alacsony"
    elif t.risk == "high":
        risk_emoji = "🔴"
        risk_text = "magas"
    else:
        risk_emoji = "🟠"
        risk_text = "közepes"

    if m.odds_home and m.odds_draw and m.odds_away:
        odds_str = f"{m.odds_home:.2f} / {m.odds_draw:.2f} / {m.odds_away:.2f}"
    else:
        odds_str = "n/a"

    prefix = f"{idx}. "
    if kiemelt:
        prefix += "💎 KIEMELT – "

    return (
        f"{prefix}{fixture_part} {id_part}\n"
        f"🎯 Tipp: {tip_text}\n"
        f"📊 Odds (1/X/2): {odds_str}\n"
        f"⚠️ Kockázat: {risk_emoji} {risk_text}\n"
        f"💡 Bizalom: {stars} ({t.confidence}/5)\n"
        f"🧠 Miért? {t.reason}"
    )


def _tips_to_bets_list(tips: List[AiTip]) -> List[Dict[str, Any]]:
    bets: List[Dict[str, Any]] = []
    for t in tips:
        m = t.match
        if t.pick == "home":
            tip_txt = "Hazai győzelem"
        elif t.pick == "away":
            tip_txt = "Vendég győzelem"
        else:
            tip_txt = "Döntetlen"

        bets.append(
            {
                "match": f"{m.home_team} vs {m.away_team} ({m.league} {m.country}, {m.kickoff})",
                "tip": tip_txt,
                "fixture_id": m.fixture_id,
            }
        )
    return bets


# =============== PUBLIC & VIP SZÖVEGEK =====================


def _build_public_text(public_tips: List[AiTip]) -> str:
    today = os.getenv("TIPPMIX_DATE") or ""
    lines: List[str] = []
    lines.append("👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK")
    if today:
        lines.append(f"Dátum: {today}")
    lines.append("")
    if not public_tips:
        lines.append("Ma nem találtam igazán óvatos FREE tippet. "
                     "Inkább nem erőltetem a bizonytalan meccseket. 🙏")
        return "\n".join(lines)

    lines.append("Ezek a mai, óvatosabb FREE tippek:")
    lines.append("")
    for i, t in enumerate(public_tips, start=1):
        lines.append(_format_tip_line(i, t, kiemelt=False))
        lines.append("")

    lines.append("⚠️ Felelős játék: soha ne tégy fel olyan összeget, amit nem engedhetsz meg magadnak elveszíteni.")
    return "\n".join(lines)


def _build_vip_text(vip_tips: List[AiTip]) -> str:
    today = os.getenv("TIPPMIX_DATE") or ""
    lines: List[str] = []
    lines.append("🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI MA ESTÉRE 🔥")
    if today:
        lines.append(f"({today}, 5–7 gondosan válogatott VIP tipp)")
    lines.append("────────────────────────────")
    lines.append("")

    if not vip_tips:
        lines.append(
            "Ma nem találtam elég erős, kockázat-hozam arányban jó VIP tippet. "
            "Inkább kihagyjuk a napot, mint hogy gyenge meccseket erőltessünk. 🤝"
        )
        return "\n".join(lines)

    total = len(vip_tips)
    lines.append(f"Ezek a meccsek kombinálva egy erősebb, de még ésszerűen vállalható VIP szelvényt adnak:")
    lines.append(f"(Tippek száma: {total}, cél: 5–7 tipp)")
    lines.append("")

    # Top 3 kiemelt
    top3 = vip_tips[:3]
    rest = vip_tips[3:]

    if top3:
        lines.append("💎 TOP 3 KIEMELT VIP TIPP:")
        lines.append("")
        for i, t in enumerate(top3, start=1):
            lines.append(_format_tip_line(i, t, kiemelt=True))
            lines.append("")

    if rest:
        lines.append("📌 További erős VIP meccsek:")
        lines.append("")
        for i, t in enumerate(rest, start=len(top3) + 1):
            lines.append(_format_tip_line(i, t, kiemelt=False))
            lines.append("")

    lines.append(
        "⚠️ Bankroll tipp: mindig tartsd be a saját pénzkezelési szabályaidat, "
        "és ne fogadj túl nagy téttel egyetlen meccsre sem."
    )
    return "\n".join(lines)


# =============== FALLBACK (HA NINCS OPENAI) =====================


def _fallback_basic_tips(matches: List[Match]) -> Dict[str, Any]:
    """
    Egyszerű, AI nélküli fallback:
    - TOP ligákból pár hazai tipp, ahol a hazai odds <= 2.0
    - NINCS default mindenre, lehet kevesebb tipp is.
    """
    filtered: List[Match] = []
    for m in matches:
        cat = _classify_league(m.league)
        if cat not in {"top", "major"}:
            continue
        if m.odds_home is not None and m.odds_home <= 2.0:
            filtered.append(m)

    filtered = filtered[:7]

    vip_tips: List[AiTip] = []
    for m in filtered:
        vip_tips.append(
            AiTip(
                match=m,
                pick="home",
                confidence=3,
                risk="medium",
                reason="A hazai csapat statisztikailag erősebb és az odds is ezt tükrözi.",
                vip_candidate=True,
            )
        )

    public_tips = vip_tips[:3]

    return {
        "vip_tips": vip_tips,
        "public_tips": public_tips,
    }


# =============== FŐ FÜGGVÉNY – EZT HÍVJA main.py =====================


def generate_tips(raw_matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    main.py innen kapja az adatot.
    Bemenet: sport API meccslista (dict-ek).
    Kimenet:
      {
        "telegram_public_text": "...",
        "telegram_vip_text": "...",
        "public_bets": [...],
        "vip_bets": [...]
      }
    """
    matches = [Match.from_dict(m) for m in raw_matches]

    # 1) AI hívás vagy fallback
    raw_ai = _call_openai_for_tips(matches)
    if raw_ai:
        ai_tips = _parse_ai_tips(matches, raw_ai)
    else:
        fb = _fallback_basic_tips(matches)
        ai_tips = fb["vip_tips"]

    if not ai_tips:
        # teljes vészhelyzet: nincs AI és fallback sem adott semmit
        public_text = "Ma sajnos nem sikerült érdemi tippeket generálni."
        vip_text = public_text
        return {
            "telegram_public_text": public_text,
            "telegram_vip_text": vip_text,
            "public_bets": [],
            "vip_bets": [],
        }

    # 2) pontozás, rendezés
    ai_tips_sorted = sorted(ai_tips, key=_score_tip, reverse=True)

    # VIP: max 7
    vip_tips = ai_tips_sorted[:7]

    # FREE: óvatosabb meccsek a VIP halmazból vagy a teljesből
    low_medium = [t for t in ai_tips_sorted if t.risk in {"low", "medium"}]
    public_tips = low_medium[:5]

    # 3) szövegek + recap listák
    public_text = _build_public_text(public_tips)
    vip_text = _build_vip_text(vip_tips)

    public_bets = _tips_to_bets_list(public_tips)
    vip_bets = _tips_to_bets_list(vip_tips)

    return {
        "telegram_public_text": public_text,
        "telegram_vip_text": vip_text,
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
