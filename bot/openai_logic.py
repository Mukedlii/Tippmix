import os
import json
import random
import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

client = OpenAI()

# ------------------------------ SYSTEM PROMPT ------------------------------

SYSTEM_PROMPT = """
Te a Szelvénykirály sportfogadási AI vagy. Feladatod, hogy focimeccsekre az 1X2 piacon adj tippeket FREE és VIP csatornára.

KIMENETI SZABÁLYOK (nagyon szigorú):
- Csak három féle kimenet használható magyarul:
  * "Hazai győzelem"
  * "Döntetlen"
  * "Vendég győzelem"
- TILOS bármilyen más piac vagy kombináció (1X, X2, 12, gólok, hendikep, BTTS stb.)
- A JSON-on kívül SEMMIT nem írhatsz.

PROFI / ÜGYNÖK MÓD:
A döntést professzionális elemzőként hozd meg belső checklista alapján (ezt NEM írod ki):
1) Adatminőség: csak olyan meccshez adj tippet, ahol van odds és a piac nem “zajos”.
2) Piaci baseline: implied valószínűségek legyenek az alap.
3) Ligaminőség: preferáld a top ligákat és első osztályt.
4) Döntetlen-kerülés: döntetlen csak kivételesen.
5) Short-term találati arány fókusz: egyértelmű favoritokat preferálj.
6) Kockázat és bizalom legyen konzisztens az odds/valószínűség alapján.

KIMENET:
Adj vissza egy JSON objektumot pontosan ebben a szerkezetben:

{
  "free_tips": [
    {
      "fixture_id": 123,
      "selection": "Hazai győzelem",
      "is_highlighted": false,
      "confidence": 4.0,
      "risk_level": "közepes",
      "reason": "Rövid magyar indoklás...",
      "odds_estimate": 1.75
    }
  ],
  "vip_tips": [
    {
      "fixture_id": 456,
      "selection": "Vendég győzelem",
      "is_highlighted": true,
      "confidence": 4.8,
      "risk_level": "alacsony",
      "reason": "Rövid magyar indoklás...",
      "odds_estimate": 1.65
    }
  ]
}

- risk_level: "alacsony" | "közepes" | "magas"
- confidence: 1.0–5.0
- odds_estimate lehet null/0, ha nem tudsz.
- Inkább kevesebb, de erősebb tipp. Ha kell: üres lista (NO BET).
"""

# ------------------------------ JSON SCHEMA ------------------------------

TIPS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "free_tips": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fixture_id": {"type": "integer"},
                    "selection": {"type": "string", "enum": ["Hazai győzelem", "Döntetlen", "Vendég győzelem"]},
                    "is_highlighted": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "risk_level": {"type": "string", "enum": ["alacsony", "közepes", "magas"]},
                    "reason": {"type": "string"},
                    "odds_estimate": {"type": ["number", "null"]},
                },
                "required": ["fixture_id", "selection", "is_highlighted", "confidence", "risk_level", "reason", "odds_estimate"],
            },
        },
        "vip_tips": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fixture_id": {"type": "integer"},
                    "selection": {"type": "string", "enum": ["Hazai győzelem", "Döntetlen", "Vendég győzelem"]},
                    "is_highlighted": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "risk_level": {"type": "string", "enum": ["alacsony", "közepes", "magas"]},
                    "reason": {"type": "string"},
                    "odds_estimate": {"type": ["number", "null"]},
                },
                "required": ["fixture_id", "selection", "is_highlighted", "confidence", "risk_level", "reason", "odds_estimate"],
            },
        },
    },
    "required": ["free_tips", "vip_tips"],
}

# ------------------------------ BASIC HELPERS ------------------------------

def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _normalize_match(raw: Dict[str, Any]) -> Dict[str, Any]:
    fixture_id = raw.get("fixture_id") or raw.get("id")
    try:
        fixture_id = int(fixture_id) if fixture_id is not None else None
    except Exception:
        fixture_id = None

    league = (
        raw.get("league_name")
        or raw.get("league")
        or (raw.get("league") or {}).get("name")
        or "Ismeretlen liga"
    )
    country = raw.get("country") or (raw.get("league") or {}).get("country") or ""

    teams = raw.get("teams") or {}
    home_team = raw.get("home_team") or (teams.get("home") or {}).get("name") or "Hazai csapat"
    away_team = raw.get("away_team") or (teams.get("away") or {}).get("name") or "Vendég csapat"

    kickoff = (
        raw.get("kickoff_local")
        or raw.get("kickoff")
        or raw.get("datetime")
        or raw.get("date")
        or (raw.get("fixture") or {}).get("date")
    )
    kickoff_str = str(kickoff) if kickoff is not None else "Ismeretlen időpont"

    odds = raw.get("odds") or {}
    odds_1 = _safe_float(odds.get("1") or odds.get("home") or raw.get("odds_1"))
    odds_x = _safe_float(odds.get("X") or odds.get("draw") or raw.get("odds_x"))
    odds_2 = _safe_float(odds.get("2") or odds.get("away") or raw.get("odds_2"))

    return {
        "fixture_id": fixture_id,
        "league": str(league),
        "country": str(country),
        "home_team": str(home_team),
        "away_team": str(away_team),
        "kickoff": kickoff_str,
        "odds_1": odds_1,
        "odds_x": odds_x,
        "odds_2": odds_2,
    }


def _matches_for_llm(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_normalize_match(m) for m in matches]


# ------------------------------ ODDS / MARKET LOGIC ------------------------------

TOP_LEAGUE_HINTS = [
    "Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1",
    "Eredivisie", "Primeira Liga", "Championship",
    "UEFA", "Champions League", "Europa League", "Conference League",
    "MLS", "NB I", "OTP Bank Liga",
]
BAD_LEAGUE_HINTS = ["Friendly", "Barátságos", "U19", "U20", "U21", "U23", "Reserve", "B csapat"]


def _is_topish_league(name: str) -> bool:
    n = (name or "").lower()
    if any(x.lower() in n for x in BAD_LEAGUE_HINTS):
        return False
    return any(x.lower() in n for x in TOP_LEAGUE_HINTS)


def _implied_probs(odds_1: Optional[float], odds_x: Optional[float], odds_2: Optional[float]) -> Optional[Dict[str, float]]:
    if not odds_1 or not odds_x or not odds_2:
        return None
    if odds_1 <= 1.01 or odds_x <= 1.01 or odds_2 <= 1.01:
        return None

    p1 = 1.0 / odds_1
    px = 1.0 / odds_x
    p2 = 1.0 / odds_2
    s = p1 + px + p2
    if s <= 0:
        return None

    return {"p1": p1 / s, "px": px / s, "p2": p2 / s, "overround": s - 1.0}


def _market_favorite(implied: Dict[str, float]) -> Tuple[str, float, float]:
    items = [
        ("Hazai győzelem", implied["p1"]),
        ("Döntetlen", implied["px"]),
        ("Vendég győzelem", implied["p2"]),
    ]
    items.sort(key=lambda x: x[1], reverse=True)
    top_sel, top_p = items[0]
    second_p = items[1][1]
    return top_sel, top_p, (top_p - second_p)


def _default_risk_and_conf(p_top: float, edge: float, top_league: bool) -> Tuple[str, float]:
    if p_top >= 0.60 and edge >= 0.10 and top_league:
        risk = "alacsony"
    elif p_top >= 0.54 and edge >= 0.07:
        risk = "közepes"
    else:
        risk = "magas"

    conf = 1.0 + 8.0 * (p_top - 0.33)
    conf += 5.0 * edge
    if top_league:
        conf += 0.2
    conf = max(1.0, min(5.0, conf))
    return risk, conf


def _prefilter_matches(matches_norm: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    slot = (slot or "DAY").upper()

    for m in matches_norm:
        implied = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        if not implied:
            continue

        # túl zajos piac kiszűrése
        if implied["overround"] > 0.14:
            continue

        top_sel, p_top, edge = _market_favorite(implied)
        top_league = _is_topish_league(m.get("league") or "")

        # nappal szigorúbb: kis ligák OFF
        if slot == "DAY" and not top_league:
            continue

        # legyen egyértelmű favorit
        if p_top < (0.56 if slot == "DAY" else 0.54):
            continue
        if edge < (0.08 if slot == "DAY" else 0.07):
            continue

        # döntetlen kerülés
        if top_sel == "Döntetlen" and not (p_top >= 0.34 and edge >= 0.09 and top_league):
            continue

        mm = dict(m)
        mm["implied"] = implied
        mm["market_favorite"] = top_sel
        mm["market_p_top"] = float(p_top)
        mm["market_edge"] = float(edge)
        mm["top_league"] = bool(top_league)
        out.append(mm)

    out.sort(
        key=lambda x: (
            1 if x.get("top_league") else 0,
            x.get("market_p_top") or 0.0,
            x.get("market_edge") or 0.0,
        ),
        reverse=True,
    )
    return out


# ------------------------------ TELEGRAM FORMATTING ------------------------------

def _risk_to_emoji(risk: str) -> str:
    r = (risk or "").lower()
    if "alacsony" in r:
        return "🟢 alacsony"
    if "magas" in r:
        return "🔴 magas"
    return "🟠 közepes"


def _confidence_to_stars(conf: float) -> str:
    try:
        c = float(conf)
    except Exception:
        c = 3.0
    c = max(1.0, min(5.0, c))
    full = int(round(c))
    return "⭐" * full + f" ({c:.1f}/5)"


def _build_match_label(m: Dict[str, Any]) -> str:
    league_country = m["league"]
    if m.get("country"):
        league_country += f" {m['country']}"
    return f"{m['home_team']} vs {m['away_team']} ({league_country}, {m['kickoff']})"


# ------------------------------ OPENAI CALLS ------------------------------

def _should_use_responses(model_name: str) -> bool:
    env = (os.getenv("TIPPMIX_USE_RESPONSES", "") or "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    return model_name.startswith("gpt-5")


def _call_openai_primary(matches_norm: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = os.getenv("TIPPMIX_SLOT", "DAY").upper()
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    model_name = os.getenv("TIPPMIX_MODEL", "gpt-4.1-mini")
    reasoning_effort = os.getenv("TIPPMIX_REASONING_EFFORT", "low")
    verbosity = os.getenv("TIPPMIX_VERBOSITY", "low")

    shortlist = _prefilter_matches(matches_norm, slot)

    # ha túl kevés, lazítás: csak odds + overround
    if len(shortlist) < 10:
        tmp: List[Dict[str, Any]] = []
        for m in matches_norm:
            implied = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
            if not implied or implied["overround"] > 0.16:
                continue
            top_sel, p_top, edge = _market_favorite(implied)
            mm = dict(m)
            mm["implied"] = implied
            mm["market_favorite"] = top_sel
            mm["market_p_top"] = float(p_top)
            mm["market_edge"] = float(edge)
            mm["top_league"] = _is_topish_league(m.get("league") or "")
            tmp.append(mm)
        tmp.sort(key=lambda x: (x["top_league"], x["market_p_top"], x["market_edge"]), reverse=True)
        shortlist = tmp[:30]
    else:
        shortlist = shortlist[:30]

    user_payload = []
    for m in shortlist:
        implied = m.get("implied") or {}
        user_payload.append({
            "fixture_id": m["fixture_id"],
            "league": m["league"],
            "country": m.get("country", ""),
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "kickoff": m["kickoff"],
            "odds_1": m.get("odds_1"),
            "odds_x": m.get("odds_x"),
            "odds_2": m.get("odds_2"),
            "market_favorite": m.get("market_favorite"),
            "market_p_top": round(float(m.get("market_p_top") or 0.0), 4),
            "market_edge": round(float(m.get("market_edge") or 0.0), 4),
            "overround": round(float(implied.get("overround") or 0.0), 4),
            "top_league": bool(m.get("top_league")),
        })

    user_prompt = (
        f"Mai dátum: {today}\n"
        f"Idősáv: {slot_text}\n\n"
        "Itt egy előszűrt shortlist a mai meccsekből (odds + implied prob + edge alapján).\n"
        "Feladatod:\n"
        "- Adj 2–5 FREE és 3–7 VIP tippet.\n"
        "- VIP-ben pontosan 3 legyen KIEMELT (is_highlighted=true) és ezek legyenek a legstabilabbak.\n"
        "- Short-term találati arány fókusz: preferáld a piaci favoritot és az egyértelmű meccseket.\n"
        "- Döntetlenre csak kivételesen tippelj.\n"
        "- reason: 1-2 mondat, konkrét (p_top, edge, liga) indoklás.\n"
        "- odds_estimate: a választott kimenet odds-a (ha ismert), különben null.\n\n"
        "Shortlist JSON:\n"
        f"{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n\n"
        "KIZÁRÓLAG JSON-t adj vissza a megadott struktúrában."
    )

    if _should_use_responses(model_name):
        resp = client.responses.create(
            model=model_name,
            reasoning={"effort": reasoning_effort},
            instructions=SYSTEM_PROMPT,
            input=[{"role": "user", "content": user_prompt}],
            text={
                "verbosity": verbosity,
                "format": {
                    "type": "json_schema",
                    "name": "tippmix_tips",
                    "schema": TIPS_SCHEMA,
                    "strict": True,
                },
            },
        )
        content = getattr(resp, "output_text", None) or ""
        if not content:
            try:
                content = resp.output[0].content[0].text
            except Exception:
                content = ""
    else:
        kwargs: Dict[str, Any] = {}
        # csak nem-gpt-5 esetben használunk temperature-t
        if not model_name.startswith("gpt-5"):
            kwargs["temperature"] = float(os.getenv("TIPPMIX_TEMP", "0.25"))

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "tippmix_tips", "schema": TIPS_SCHEMA, "strict": True}},
            **kwargs,
        )
        content = response.choices[0].message.content or ""

    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("LLM JSON root is not an object")
    return data


def _call_openai_with_fallback(matches_norm: List[Dict[str, Any]]) -> Dict[str, Any]:
    primary = os.getenv("TIPPMIX_MODEL", "gpt-4.1-mini")
    fallback = os.getenv("TIPPMIX_FALLBACK_MODEL", "gpt-4.1-mini")

    try:
        return _call_openai_primary(matches_norm)
    except Exception as e:
        msg = str(e).lower()

        retryable = any(x in msg for x in [
            "model", "not found", "insufficient", "permission",
            "rate limit", "quota", "overloaded", "timeout", "503", "429", "403", "404"
        ])

        print(f"[OpenAI] Primary model failed: {primary} | Error: {repr(e)}")

        if (not retryable) or (primary == fallback):
            raise

        print(f"[OpenAI] Falling back to: {fallback}")
        os.environ["TIPPMIX_MODEL"] = fallback
        try:
            return _call_openai_primary(matches_norm)
        finally:
            os.environ["TIPPMIX_MODEL"] = primary


# ------------------------------ FALLBACK TIPS (NO AI) ------------------------------

def _fallback_tips(matches_norm: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not matches_norm:
        return [], []

    allowed_selections = ["Hazai győzelem", "Döntetlen", "Vendég győzelem"]
    random.shuffle(matches_norm)
    take = min(6, len(matches_norm))
    chosen = matches_norm[:take]

    vip_raw: List[Dict[str, Any]] = []
    free_raw: List[Dict[str, Any]] = []

    for idx, m in enumerate(chosen):
        sel = random.choice(allowed_selections)
        base = {
            "fixture_id": m["fixture_id"],
            "selection": sel,
            "is_highlighted": idx < 3,
            "confidence": 3.0,
            "risk_level": "közepes",
            "reason": "Fallback tipp (AI válasz nem volt stabil / elérhető).",
            "odds_estimate": None,
        }
        if idx < 3:
            vip_raw.append(base)
        else:
            free_raw.append(base)

    return vip_raw, free_raw


# ------------------------------ POST GUARDRAILS ------------------------------

def _enforce_vip_highlights(vips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not vips:
        return vips
    vips_sorted = sorted(vips, key=lambda t: float(t.get("confidence") or 0.0), reverse=True)
    for t in vips_sorted:
        t["is_highlighted"] = False
    for t in vips_sorted[:3]:
        t["is_highlighted"] = True
    return vips_sorted


def _drop_weird_picks(tips: List[Dict[str, Any]], id_to_match: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for t in tips:
        m = id_to_match.get(t["fixture_id"])
        if not m:
            continue
        implied = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        if not implied:
            continue

        fav, p_top, edge = _market_favorite(implied)

        # amíg nincs forma/xG/sérülés adat, ne menj piac ellen
        if t["selection"] != fav:
            continue

        if t["selection"] == "Döntetlen" and not (p_top >= 0.34 and edge >= 0.09 and _is_topish_league(m.get("league") or "")):
            continue

        top_league = _is_topish_league(m.get("league") or "")
        risk, conf = _default_risk_and_conf(p_top, edge, top_league)
        t["risk_level"] = risk
        t["confidence"] = conf

        cleaned.append(t)
    return cleaned


# ------------------------------ MAIN ENTRY ------------------------------

def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not matches:
        return {
            "telegram_public_text": "Ma sajnos nem találtam érdemi FREE tippet.",
            "telegram_vip_text": "Ma sajnos nem találtam érdemi VIP tippet.",
            "public_bets": [],
            "vip_bets": [],
        }

    matches_norm = _matches_for_llm(matches)
    id_to_match: Dict[int, Dict[str, Any]] = {
        m["fixture_id"]: m for m in matches_norm if m.get("fixture_id") is not None
    }

    free_raw: List[Dict[str, Any]] = []
    vip_raw: List[Dict[str, Any]] = []

    try:
        ai_data = _call_openai_with_fallback(matches_norm)
        free_raw = ai_data.get("free_tips") or []
        vip_raw = ai_data.get("vip_tips") or []
    except Exception as e:
        print("Hiba az OpenAI hívásnál (még fallback után is):", repr(e))
        free_raw, vip_raw = [], []

    # Ha az AI semmit nem adott
    if not free_raw and not vip_raw:
        print("LLM nem adott vissza használható tippeket, fallback logika lép életbe.")
        vip_raw, free_raw = _fallback_tips(matches_norm)

    allowed_selections = {"Hazai győzelem", "Döntetlen", "Vendég győzelem"}

    def _clean_list(raw_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned: List[Dict[str, Any]] = []
        for item in raw_list:
            try:
                fid = int(item.get("fixture_id"))
            except Exception:
                continue
            if fid not in id_to_match:
                continue

            sel = (item.get("selection") or "").strip()
            if sel not in allowed_selections:
                continue

            cleaned.append(
                {
                    "fixture_id": fid,
                    "selection": sel,
                    "is_highlighted": bool(item.get("is_highlighted", False)),
                    "confidence": _safe_float(item.get("confidence")) or 3.0,
                    "risk_level": (item.get("risk_level") or "közepes").lower(),
                    "reason": (item.get("reason") or "").strip(),
                    "odds_estimate": _safe_float(item.get("odds_estimate")),
                }
            )
        return cleaned

    vip_tips = _clean_list(vip_raw)
    free_tips = _clean_list(free_raw)

    # post-guardrails (stabil hitrate felé)
    vip_tips = _drop_weird_picks(vip_tips, id_to_match)
    free_tips = _drop_weird_picks(free_tips, id_to_match)

    # VIP highlight kivasalás
    vip_tips = _enforce_vip_highlights(vip_tips)
    for t in free_tips:
        t["is_highlighted"] = False

    # limit
    if len(vip_tips) > 7:
        vip_tips = vip_tips[:7]
    if len(free_tips) > 5:
        free_tips = free_tips[:5]

    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = os.getenv("TIPPMIX_SLOT", "DAY").upper()
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    # --- VIP TELEGRAM ---
    vip_lines: List[str] = []
    vip_lines.append("🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI 🔥")
    vip_lines.append(f"Dátum: {today}")
    vip_lines.append(f"Idősáv: {slot_text}")
    vip_lines.append(f"Tippek száma: {len(vip_tips)}")
    vip_lines.append("────────────────────")

    if vip_tips:
        ordered = sorted(vip_tips, key=lambda t: (not t["is_highlighted"], -t["confidence"]))
        for idx, tip in enumerate(ordered, start=1):
            m = id_to_match.get(tip["fixture_id"])
            match_label = _build_match_label(m) if m else f"Fixture ID={tip['fixture_id']}"
            highlight_prefix = "💎 KIEMELT – " if tip["is_highlighted"] else ""
            odds_txt = f"{tip['odds_estimate']:.2f}" if tip["odds_estimate"] else "n/a"
            risk_txt = _risk_to_emoji(tip["risk_level"])
            conf_txt = _confidence_to_stars(tip["confidence"])
            reason = tip["reason"] or "Odds/valószínűség/edge és ligaminőség alapján ez a legstabilabb opciónak tűnik."

            vip_lines.append(
                f"{idx}. {highlight_prefix}{match_label}\n"
                f"🎯 Tipp: {tip['selection']}\n"
                f"📊 Odds (1X2): {odds_txt}\n"
                f"⚠️ Kockázat: {risk_txt}\n"
                f"💡 Bizalom: {conf_txt}\n"
                f"🧠 Miért? {reason}"
            )
    else:
        vip_lines.append("Ma nem találtam elég erős VIP tippet, inkább nem erőltetem a játékot.")

    telegram_vip_text = "\n\n".join(vip_lines)

    # --- FREE TELEGRAM ---
    free_lines: List[str] = []
    free_lines.append("👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK")
    free_lines.append(f"Dátum: {today}")
    free_lines.append(f"Idősáv: {slot_text}")
    free_lines.append("Ezek a mai, óvatosabb FREE tippek:")
    free_lines.append("────────────────────")

    if free_tips:
        ordered_f = sorted(free_tips, key=lambda t: -t["confidence"])
        for idx, tip in enumerate(ordered_f, start=1):
            m = id_to_match.get(tip["fixture_id"])
            match_label = _build_match_label(m) if m else f"Fixture ID={tip['fixture_id']}"
            odds_txt = f"{tip['odds_estimate']:.2f}" if tip["odds_estimate"] else "n/a"
            risk_txt = _risk_to_emoji(tip["risk_level"])
            conf_txt = _confidence_to_stars(tip["confidence"])
            reason = tip["reason"] or "Odds/valószínűség/edge alapján statisztikailag ígéretes mérkőzés."

            free_lines.append(
                f"{idx}. {match_label}\n"
                f"🎯 Tipp: {tip['selection']}\n"
                f"📊 Odds (1X2): {odds_txt}\n"
                f"⚠️ Kockázat: {risk_txt}\n"
                f"💡 Bizalom: {conf_txt}\n"
                f"🧠 Miért? {reason}"
            )
    else:
        free_lines.append("Ma sajnos nem sikerült érdemi FREE tippeket generálni.")

    telegram_public_text = "\n\n".join(free_lines)

    # --- JSON recap-hez / mentéshez ---
    vip_bets: List[Dict[str, Any]] = []
    for tip in vip_tips:
        m = id_to_match.get(tip["fixture_id"])
        match_label = _build_match_label(m) if m else f"Fixture ID={tip['fixture_id']}"
        vip_bets.append({"fixture_id": tip["fixture_id"], "match": match_label, "tip": tip["selection"]})

    public_bets: List[Dict[str, Any]] = []
    for tip in free_tips:
        m = id_to_match.get(tip["fixture_id"])
        match_label = _build_match_label(m) if m else f"Fixture ID={tip['fixture_id']}"
        public_bets.append({"fixture_id": tip["fixture_id"], "match": match_label, "tip": tip["selection"]})

    return {
        "telegram_public_text": telegram_public_text,
        "telegram_vip_text": telegram_vip_text,
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
