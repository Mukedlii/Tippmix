# -*- coding: utf-8 -*-
"""
Szöveg + tipp generálás SZELVÉNYKIRÁLY bothoz.

FONTOS:
- NEM használ OpenAI / LLM API-t.
- A döntéseket teljesen a sport API-ból jövő meccs + odds adatok alapján hozza.
- Kimenet kompatibilis a main.py + recap kóddal (public_bets / vip_bets).
"""

import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Adattípusok
# ---------------------------------------------------------------------------

@dataclass
class MatchInfo:
    raw: Dict[str, Any]
    fixture_id: int
    home_team: str
    away_team: str
    league_name: str
    country: str
    kickoff_raw: Any
    kickoff_str: str
    odds_1: Optional[float]
    odds_x: Optional[float]
    odds_2: Optional[float]


@dataclass
class TipCandidate:
    match: MatchInfo
    outcome: str          # "home", "draw", "away"
    tip_text: str         # pl. "Hazai győzelem"
    chosen_odds: Optional[float]
    prob: float           # 0–1, favorit valószínűség (durva)
    league_weight: float  # 0.5–1.1
    score: float          # rendezéshez
    confidence: float     # 1–5
    risk_level: str       # "low" / "medium" / "high"


# ---------------------------------------------------------------------------
# Parszoló segédek
# ---------------------------------------------------------------------------

def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_fixture_id(m: Dict[str, Any]) -> Optional[int]:
    """Próbáljuk kivenni a fixture ID-t több lehetséges mezőből."""
    for key in ("fixture_id", "id"):
        if key in m:
            try:
                return int(m[key])
            except Exception:
                pass

    fixture = m.get("fixture") or {}
    for key in ("id", "fixture_id"):
        if key in fixture:
            try:
                return int(fixture[key])
            except Exception:
                pass

    return None


def _parse_teams(m: Dict[str, Any]) -> Tuple[str, str]:
    """Hazai / vendég csapat neve több formátum támogatásával."""
    home = ""
    away = ""

    if "teams" in m:
        teams = m["teams"] or {}
        home = _safe_str((teams.get("home") or {}).get("name") or home)
        away = _safe_str((teams.get("away") or {}).get("name") or away)

    home = _safe_str(m.get("home_team") or home)
    away = _safe_str(m.get("away_team") or away)

    return home or "Hazai csapat", away or "Vendég csapat"


def _parse_league(m: Dict[str, Any]) -> Tuple[str, str]:
    league_name = ""
    country = ""

    league = m.get("league") or {}
    league_name = _safe_str(league.get("name") or m.get("league_name") or "")
    country = _safe_str(league.get("country") or m.get("country") or "")

    if not league_name:
        league_name = "Ismeretlen liga"
    if not country:
        country = "World"

    return league_name, country


def _parse_kickoff(m: Dict[str, Any]) -> Tuple[Any, str]:
    """
    Kickoff időt próbáljuk szépen formázni.
    Ha nem tudjuk rendesen, visszaadjuk "időpont ismeretlen" szöveggel.
    """
    dt_raw = (
        m.get("kickoff_local")
        or m.get("kickoff")
        or m.get("datetime")
        or (m.get("fixture") or {}).get("date")
        or m.get("date")
    )

    if isinstance(dt_raw, datetime.datetime):
        local_dt = dt_raw
    elif isinstance(dt_raw, str):
        s = dt_raw.strip()
        # ISO formátum
        try:
            local_dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            # "2025-12-17T18:00:00" jellegű
            if "T" in s:
                date_part, time_part = s.split("T", 1)
                try:
                    d = datetime.date.fromisoformat(date_part)
                except Exception:
                    d = datetime.date.today()
                t_parts = time_part.split(":")
                try:
                    h = int(t_parts[0])
                    mi = int(t_parts[1]) if len(t_parts) > 1 else 0
                except Exception:
                    h, mi = 0, 0
                local_dt = datetime.datetime(d.year, d.month, d.day, h, mi)
            else:
                # esetleg csak "HH:MM"
                t_parts = s.split(":")
                try:
                    h = int(t_parts[0])
                    mi = int(t_parts[1]) if len(t_parts) > 1 else 0
                    today = datetime.date.today()
                    local_dt = datetime.datetime(today.year, today.month, today.day, h, mi)
                except Exception:
                    local_dt = None
    else:
        local_dt = None

    if local_dt is None:
        return dt_raw, "időpont ismeretlen"

    return local_dt, local_dt.strftime("%H:%M")


def _parse_odds(m: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    1X2 oddsok kinyerése.
    Próbál több lehetséges kulcsot, hogy rugalmas legyen.
    """
    odds_1 = odds_x = odds_2 = None

    # lapos mezők
    for key in ("odd_1", "home_win", "home", "odds_1"):
        if key in m and odds_1 is None:
            try:
                odds_1 = float(m[key])
            except Exception:
                pass

    for key in ("odd_x", "draw", "odds_x"):
        if key in m and odds_x is None:
            try:
                odds_x = float(m[key])
            except Exception:
                pass

    for key in ("odd_2", "away_win", "away", "odds_2"):
        if key in m and odds_2 is None:
            try:
                odds_2 = float(m[key])
            except Exception:
                pass

    # esetleges beágyazott dict (egyszerűsítve)
    nested_odds = m.get("odds") or m.get("bookmakers") or {}
    if isinstance(nested_odds, dict):
        for k, v in nested_odds.items():
            if not isinstance(v, (int, float, str)):
                continue
            try:
                val = float(v)
            except Exception:
                continue
            lk = k.lower()
            if "home" in lk and odds_1 is None:
                odds_1 = val
            elif "draw" in lk and odds_x is None:
                odds_x = val
            elif "away" in lk and odds_2 is None:
                odds_2 = val

    return odds_1, odds_x, odds_2


def _league_weight(league_name: str, country: str) -> float:
    """
    Liga súly: top európai ligák kapnak pluszt,
    U19 / barátságos / alsóbb ligák mínuszt.
    """
    ln = league_name.lower()
    c = country.lower()

    top_keywords = [
        "premier league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "champions league",
        "europa league",
        "conference league",
        "eredivisie",
        "primeira liga",
        "championship",
    ]

    weak_keywords = [
        "friendly",
        "u19",
        "u20",
        "u21",
        "u22",
        "u23",
        "youth",
        "reserve",
        "2. liga",
        "liga ii",
        "liga 2",
        "3. liga",
        "liga iii",
    ]

    weight = 1.0

    if any(k in ln for k in top_keywords):
        weight += 0.1

    if any(k in ln for k in weak_keywords):
        weight -= 0.2

    if c in {"england", "spain", "germany", "italy", "france", "netherlands", "portugal"}:
        weight += 0.05

    return max(0.5, min(1.1, weight))


# ---------------------------------------------------------------------------
# Kockázat + bizalom + score
# ---------------------------------------------------------------------------

def _risk_and_confidence(
    odds: Optional[float], league_weight: float
) -> Tuple[str, float]:
    """
    Visszaad: (risk_level, confidence 1–5)
    """
    if odds is None:
        # nincs odds -> közepes
        base_conf = 3.0
        risk = "medium"
    else:
        if odds < 1.25:
            base_conf = 4.0
            risk = "low"
        elif odds < 1.45:
            base_conf = 4.3
            risk = "low"
        elif odds < 1.75:
            base_conf = 4.0
            risk = "medium"
        elif odds < 2.2:
            base_conf = 3.5
            risk = "medium"
        elif odds < 2.8:
            base_conf = 3.0
            risk = "high"
        else:
            base_conf = 2.5
            risk = "high"

    base_conf *= league_weight
    base_conf = max(1.5, min(5.0, base_conf))
    return risk, base_conf


def _score_candidate(
    prob: float,
    odds: Optional[float],
    league_weight: float,
    confidence: float,
) -> float:
    """
    Összpontszám, amire rendezünk:
    - nagyobb valószínűség jobb
    - „fertőzött” ligák gyengébb súly
    - extrém alacsony / nagyon magas odds se legyen túl erős
    """
    if odds is None:
        return prob * league_weight * (0.8 + confidence / 5.0)

    if odds < 1.15:
        odds_factor = 0.5
    elif odds < 1.3:
        odds_factor = 0.9
    elif odds < 1.6:
        odds_factor = 1.1
    elif odds < 2.1:
        odds_factor = 1.0
    elif odds < 2.6:
        odds_factor = 0.9
    else:
        odds_factor = 0.6

    return prob * league_weight * odds_factor * (0.7 + confidence / 5.0)


# ---------------------------------------------------------------------------
# Szövegek (magyar, emojikkal)
# ---------------------------------------------------------------------------

def _build_reason_text(
    outcome: str,
    match: MatchInfo,
    risk: str,
    confidence: float,
) -> str:
    if outcome == "home":
        base = (
            f"A(z) {match.home_team} hazai pályán erősebbnek tűnik, "
            f"miközben a(z) {match.away_team} idegenben bizonytalanabb teljesítményt nyújt."
        )
    elif outcome == "away":
        base = (
            f"A(z) {match.away_team} formája és kerete alapján "
            f"jobb választásnak tűnik a(z) {match.home_team} ellen, "
            f"különösen az utóbbi mérkőzéseket nézve."
        )
    else:  # draw
        base = (
            "A statisztikák kiegyenlített mérkőzést jeleznek, "
            "mindkét csapat hasonló erősségű, ezért a döntetlen is reális kimenetel."
        )

    if risk == "low":
        base += " Az odds és a liga erőssége alapján ez inkább óvatosabb, stabilabb tipp."
    elif risk == "high":
        base += " A kockázat magasabb, de az odds cserébe vonzóbb lehet a bátrabb játékosoknak."

    if confidence >= 4.5:
        base += " Az összkép erős, ezért prémium szintű tippnek tekinthető."
    elif confidence <= 2.5:
        base += " Összességében inkább óvatosan kezelendő, nem elsődleges választás."

    return base


def _stars_from_confidence(conf: float) -> Tuple[str, float]:
    """Csillagos megjelenítés 0.5 lépésközzel."""
    rounded = round(conf * 2) / 2.0
    full = int(rounded)
    half = 1 if rounded - full >= 0.5 else 0
    empty = 5 - full - half

    stars = "⭐" * full + ("⭐️" if half else "") + "☆" * empty
    return stars, rounded


def _risk_emoji(risk: str) -> str:
    if risk == "low":
        return "🟢 alacsony"
    if risk == "high":
        return "🔴 magas"
    return "🟡 közepes"


# ---------------------------------------------------------------------------
# Candidate építés
# ---------------------------------------------------------------------------

def _build_match_info(m: Dict[str, Any]) -> Optional[MatchInfo]:
    fixture_id = _parse_fixture_id(m)
    if fixture_id is None:
        return None

    home, away = _parse_teams(m)
    league_name, country = _parse_league(m)
    kickoff_raw, kickoff_str = _parse_kickoff(m)
    odds_1, odds_x, odds_2 = _parse_odds(m)

    return MatchInfo(
        raw=m,
        fixture_id=fixture_id,
        home_team=home,
        away_team=away,
        league_name=league_name,
        country=country,
        kickoff_raw=kickoff_raw,
        kickoff_str=kickoff_str,
        odds_1=odds_1,
        odds_x=odds_x,
        odds_2=odds_2,
    )


def _generate_candidates(matches: List[Dict[str, Any]]) -> List[TipCandidate]:
    candidates: List[TipCandidate] = []

    for m in matches:
        mi = _build_match_info(m)
        if mi is None:
            continue

        league_w = _league_weight(mi.league_name, mi.country)

        # Ha egyáltalán nincs odds, legyen óvatos hazai tipp
        if mi.odds_1 is None and mi.odds_x is None and mi.odds_2 is None:
            risk, conf = _risk_and_confidence(None, league_w)
            prob = 0.5
            score = _score_candidate(prob, None, league_w, conf)

            candidates.append(
                TipCandidate(
                    match=mi,
                    outcome="home",
                    tip_text="Hazai győzelem",
                    chosen_odds=None,
                    prob=prob,
                    league_weight=league_w,
                    score=score,
                    confidence=conf,
                    risk_level=risk,
                )
            )
            continue

        # Van legalább egy odds -> választunk favoritot (legalacsonyabb odds)
        odds_list: List[Tuple[str, Optional[float]]] = [
            ("home", mi.odds_1),
            ("draw", mi.odds_x),
            ("away", mi.odds_2),
        ]
        odds_list = [(o, v) for (o, v) in odds_list if v is not None]
        if not odds_list:
            continue

        outcome, best_odds = min(odds_list, key=lambda x: x[1])  # type: ignore
        prob = 1.0 / best_odds if best_odds and best_odds > 1.0 else 0.5

        risk, conf = _risk_and_confidence(best_odds, league_w)
        score = _score_candidate(prob, best_odds, league_w, conf)

        if outcome == "home":
            tip_text = "Hazai győzelem"
        elif outcome == "away":
            tip_text = "Vendég győzelem"
        else:
            tip_text = "Döntetlen"

        candidates.append(
            TipCandidate(
                match=mi,
                outcome=outcome,
                tip_text=tip_text,
                chosen_odds=best_odds,
                prob=prob,
                league_weight=league_w,
                score=score,
                confidence=conf,
                risk_level=risk,
            )
        )

    return candidates


# ---------------------------------------------------------------------------
# Szöveg generálás FREE / VIP
# ---------------------------------------------------------------------------

def _format_match_line(
    idx: int,
    tip: TipCandidate,
    highlighted: bool,
    is_vip: bool,
) -> str:
    mi = tip.match

    kickoff_part = mi.kickoff_str if mi.kickoff_str != "időpont ismeretlen" else ""
    header_flag = "💎 KIEMELT – " if highlighted and is_vip else ""
    line_header = (
        f"{idx}. {header_flag}{mi.home_team} vs {mi.away_team} "
        f"({mi.league_name} {mi.country}"
    )
    if kickoff_part:
        line_header += f", {kickoff_part}"
    line_header += f") [ID={mi.fixture_id}]"

    odds_str = f"{tip.chosen_odds:.2f}" if tip.chosen_odds is not None else "n/a"
    risk_hu = _risk_emoji(tip.risk_level)
    stars, rounded_conf = _stars_from_confidence(tip.confidence)
    reason = _build_reason_text(tip.outcome, mi, tip.risk_level, rounded_conf)

    text = (
        f"{line_header}\n"
        f"🎯 Tipp: {tip.tip_text}\n"
        f"📊 Odds (1X/2): {odds_str}\n"
        f"⚠️ Kockázat: {risk_hu}\n"
        f"💡 Bizalom: {stars} ({rounded_conf:.1f}/5)\n"
        f"🧠 Miért? {reason}\n"
    )
    return text


def _build_public_text(date_str: str, public_tips: List[TipCandidate]) -> str:
    if not public_tips:
        return (
            "Ma sajnos nem sikerült érdemi FREE tippeket generálni. "
            "Inkább kihagyjuk a gyenge értékű meccseket, minthogy erőltetett tippet küldjünk. ⚽️"
        )

    header = (
        "👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK\n"
        f"Dátum: {date_str}\n\n"
        "Ezek a mai, óvatosabb FREE tippek:\n\n"
    )

    body_parts: List[str] = []
    for idx, tip in enumerate(public_tips, start=1):
        body_parts.append(_format_match_line(idx, tip, highlighted=False, is_vip=False))

    footer = (
        "⚠️ Felelős játék: soha ne tégy fel olyan összeget, amit nem engedhetsz meg magadnak elveszíteni.\n"
    )

    return header + "\n".join(body_parts) + "\n" + footer


def _build_vip_text(date_str: str, vip_tips: List[TipCandidate]) -> str:
    if not vip_tips:
        return (
            "Ma sajnos nem sikerült elég erős VIP tippeket találni. "
            "Ha nincs minőségi érték, inkább nincs tipp, mint gyenge ajánlás. 👑⚽️"
        )

    header = (
        "🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI MA 🔥\n"
        f"Dátum: {date_str}\n"
        f"Tippek száma: {len(vip_tips)} (cél: legfeljebb 7 tipp)\n"
        "────────────────────────\n"
        "Ezek a meccsek kombinálva erősebb, de még ésszerűen vállalható kockázatú VIP "
        "szelvényt adhatnak:\n\n"
    )

    body_parts: List[str] = []
    for idx, tip in enumerate(vip_tips, start=1):
        highlighted = idx <= 3  # első 3 = kiemelt
        body_parts.append(
            _format_match_line(
                idx,
                tip,
                highlighted=highlighted,
                is_vip=True,
            )
        )

    footer = (
        "📌 Tipp: a VIP tippeket érdemes ésszel, saját bankrollodhoz igazítva játszani. "
        "Nincs 100%, de a cél a hosszú távú, stabil plusz. 💰⚽️"
    )

    return header + "\n".join(body_parts) + "\n" + footer


# ---------------------------------------------------------------------------
# Fő belépési pont: generate_tips
# ---------------------------------------------------------------------------

def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Ezt hívja a main.py.

    Visszatér:
      {
        "telegram_public_text": str,
        "telegram_vip_text": str,
        "public_bets": [ { "fixture_id": int, "match": str, "tip": str } ],
        "vip_bets":    [ { "fixture_id": int, "match": str, "tip": str } ],
      }
    """
    today = datetime.date.today()
    date_str = today.strftime("%Y.%m.%d.")

    candidates = _generate_candidates(matches)
    if not candidates:
        msg = (
            "Ma sajnos nem sikerült érdemi tippeket generálni – "
            "a sport adatok nem adtak elég erős jelet. ⚽️"
        )
        return {
            "telegram_public_text": msg,
            "telegram_vip_text": msg,
            "public_bets": [],
            "vip_bets": [],
        }

    # Rangsorolás
    candidates.sort(key=lambda c: c.score, reverse=True)

    # VIP: max. 7 tipp, legalább 3.0 bizalommal
    vip_tips: List[TipCandidate] = []
    for c in candidates:
        if c.confidence < 3.0:
            continue
        vip_tips.append(c)
        if len(vip_tips) == 7:
            break

    # Ha túl kevés maradt, engedjünk lazább szűrést
    if len(vip_tips) < 3:
        vip_tips = candidates[: min(5, len(candidates))]

    # FREE: 3–4 tipp, előnyben az alacsony kockázat + jó liga
    public_tips: List[TipCandidate] = []
    for c in candidates:
        if c.risk_level == "low" and c.confidence >= 3.2:
            public_tips.append(c)
        if len(public_tips) == 4:
            break

    if not public_tips:
        public_tips = candidates[: min(3, len(candidates))]

    public_text = _build_public_text(date_str, public_tips)
    vip_text = _build_vip_text(date_str, vip_tips)

    # JSON struktúra a recaphez
    def _bet_dict_from_tip(t: TipCandidate) -> Dict[str, Any]:
        mi = t.match
        kickoff_part = mi.kickoff_str if mi.kickoff_str != "időpont ismeretlen" else ""
        match_str = f"{mi.home_team} vs {mi.away_team} ({mi.league_name} {mi.country}"
        if kickoff_part:
            match_str += f", {kickoff_part}"
        match_str += ")"
        return {
            "fixture_id": mi.fixture_id,
            "match": match_str,
            "tip": t.tip_text,
        }

    public_bets = [_bet_dict_from_tip(t) for t in public_tips]
    vip_bets = [_bet_dict_from_tip(t) for t in vip_tips]

    return {
        "telegram_public_text": public_text,
        "telegram_vip_text": vip_text,
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
