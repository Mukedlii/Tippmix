import os
import json
import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

client = OpenAI()

DEFAULT_MIN_VIP = 6
DEFAULT_MIN_FREE = 3
MAX_VIP = 7
MAX_FREE = 5

SYSTEM_PROMPT = """
Te a Szelvénykirály sportfogadási AI vagy. Feladatod, hogy focimeccsekre az 1X2 piacon adj tippeket FREE és VIP csatornára.

SZABÁLYOK:
- Csak három kimenet:
  * "Hazai győzelem"
  * "Döntetlen"
  * "Vendég győzelem"
- Semmi más piac.
- Kizárólag JSON-t adj vissza.
- Ne találj ki oddsot: ha nem biztos, hagyd nullán.
"""

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

    league = raw.get("league_name") or (raw.get("league") or {}).get("name") or raw.get("league") or "Ismeretlen liga"
    country = raw.get("country_name") or raw.get("country") or (raw.get("league") or {}).get("country") or ""

    home_team = raw.get("home_team") or ((raw.get("teams") or {}).get("home") or {}).get("name") or "Hazai csapat"
    away_team = raw.get("away_team") or ((raw.get("teams") or {}).get("away") or {}).get("name") or "Vendég csapat"

    kickoff = raw.get("kickoff_local") or raw.get("kickoff") or raw.get("datetime") or raw.get("date") or (raw.get("fixture") or {}).get("date")
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


def _implied_probs(o1: Optional[float], ox: Optional[float], o2: Optional[float]) -> Optional[Dict[str, float]]:
    if not o1 or not ox or not o2:
        return None
    if o1 <= 1.01 or ox <= 1.01 or o2 <= 1.01:
        return None
    p1, px, p2 = 1.0 / o1, 1.0 / ox, 1.0 / o2
    s = p1 + px + p2
    if s <= 0:
        return None
    return {"p1": p1 / s, "px": px / s, "p2": p2 / s}


def _risk_conf_for_selection(m: Dict[str, Any], selection: str) -> Tuple[str, float]:
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    if not imp:
        return "közepes", 3.2

    p = imp["p1"] if selection == "Hazai győzelem" else (imp["px"] if selection == "Döntetlen" else imp["p2"])
    # skála 1..5
    conf = 1.0 + 6.0 * (p - 0.33)
    conf = max(1.0, min(5.0, conf))

    if p >= 0.60:
        risk = "alacsony"
    elif p >= 0.52:
        risk = "közepes"
    else:
        risk = "magas"

    return risk, conf


def _odds_for_selection(m: Dict[str, Any], selection: str) -> Optional[float]:
    if selection == "Hazai győzelem":
        return _safe_float(m.get("odds_1"))
    if selection == "Döntetlen":
        return _safe_float(m.get("odds_x"))
    return _safe_float(m.get("odds_2"))


def _should_use_responses() -> bool:
    v = (os.getenv("TIPPMIX_USE_RESPONSES", "1") or "").strip().lower()
    return v in ("1", "true", "yes")


def _call_llm(shortlist: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = (os.getenv("TIPPMIX_SLOT", "DAY") or "DAY").upper()
    slot_note = (os.getenv("TIPPMIX_SLOT_NOTE", "") or "").strip()

    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"
    if slot_note:
        slot_text += f" – {slot_note}"

    model = os.getenv("TIPPMIX_MODEL", "gpt-5-mini")
    min_vip = int(os.getenv("TIPPMIX_MIN_VIP", str(DEFAULT_MIN_VIP)))
    min_free = int(os.getenv("TIPPMIX_MIN_FREE", str(DEFAULT_MIN_FREE)))

    prompt = (
        f"Mai dátum: {today}\n"
        f"Idősáv: {slot_text}\n"
        f"Fizetős bot: legalább {min_free} FREE és legalább {min_vip} VIP tipp KELL.\n"
        "VIP-ben pontosan 3 legyen KIEMELT.\n"
        "Ne találj ki oddsot.\n"
        "Shortlist:\n"
        + json.dumps(shortlist, ensure_ascii=False, indent=2)
    )

    if _should_use_responses() and hasattr(client, "responses"):
        resp = client.responses.create(
            model=model,
            reasoning={"effort": os.getenv("TIPPMIX_REASONING_EFFORT", "low")},
            instructions=SYSTEM_PROMPT,
            input=[{"role": "user", "content": prompt}],
            text={
                "verbosity": os.getenv("TIPPMIX_VERBOSITY", "low"),
                "format": {"type": "json_schema", "name": "tippmix_tips", "schema": TIPS_SCHEMA, "strict": True},
            },
        )
        return json.loads(resp.output_text or "{}")

    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        temperature=float(os.getenv("TIPPMIX_TEMP", "0.25")),
        response_format={"type": "json_schema", "json_schema": {"name": "tippmix_tips", "schema": TIPS_SCHEMA, "strict": True}},
    )
    return json.loads(r.choices[0].message.content or "{}")


def _risk_to_emoji(risk: str) -> str:
    r = (risk or "").lower()
    if "alacsony" in r:
        return "🟢 alacsony"
    if "magas" in r:
        return "🔴 magas"
    return "🟠 közepes"


def _stars(conf: float) -> str:
    try:
        c = float(conf)
    except Exception:
        c = 3.0
    c = max(1.0, min(5.0, c))
    return "⭐" * int(round(c)) + f" ({c:.1f}/5)"


def _build_match_label(m: Dict[str, Any]) -> str:
    lc = m["league"]
    if m.get("country"):
        lc += f" {m['country']}"
    return f"{m['home_team']} vs {m['away_team']} ({lc}, {m['kickoff']})"


def _clean_and_override(raw_list: List[Dict[str, Any]], id_to_match: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Kritikus: az AI ne találjon ki oddsot/confidence-et.
    Itt mindent felülírunk a VALÓDI odds alapján.
    + nincs duplikált fixture.
    """
    allowed = {"Hazai győzelem", "Döntetlen", "Vendég győzelem"}
    out: List[Dict[str, Any]] = []
    seen: set[int] = set()

    for it in raw_list or []:
        try:
            fid = int(it.get("fixture_id"))
        except Exception:
            continue
        if fid not in id_to_match:
            continue
        if fid in seen:
            continue

        sel = (it.get("selection") or "").strip()
        if sel not in allowed:
            continue

        m = id_to_match[fid]
        odds_est = _odds_for_selection(m, sel)
        risk, conf = _risk_conf_for_selection(m, sel)

        out.append(
            {
                "fixture_id": fid,
                "selection": sel,
                "is_highlighted": bool(it.get("is_highlighted", False)),
                "confidence": conf,
                "risk_level": risk,
                "reason": (it.get("reason") or "Odds + összkép alapján."),
                "odds_estimate": odds_est,
            }
        )
        seen.add(fid)

    return out


def _enforce_highlights(vips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    v = sorted(vips, key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
    for t in v:
        t["is_highlighted"] = False
    for t in v[:3]:
        t["is_highlighted"] = True
    return v


def _fallback_fill(matches_norm: List[Dict[str, Any]], vip: List[Dict[str, Any]], free: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Minimum tippek feltöltése, de mindig egyedi fixture-ekkel, amíg lehet.
    Ha kevés a meccs az API-ban, akkor is feltölt, de először odds-os meccsekkel.
    """
    min_vip = int(os.getenv("TIPPMIX_MIN_VIP", str(DEFAULT_MIN_VIP)))
    min_free = int(os.getenv("TIPPMIX_MIN_FREE", str(DEFAULT_MIN_FREE)))

    used = {t["fixture_id"] for t in vip + free}

    # odds-os meccsek előre
    candidates = []
    for m in matches_norm:
        if not m.get("fixture_id"):
            continue
        imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        candidates.append((0 if imp else 1, m))
    candidates.sort(key=lambda x: x[0])

    def add(m: Dict[str, Any], is_vip: bool):
        fid = int(m["fixture_id"])
        if fid in used:
            return

        # válasszunk a 3 kimenet közül piaci favoritot, ha van odds
        imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        if imp:
            # favorit
            sel = max([("Hazai győzelem", imp["p1"]), ("Döntetlen", imp["px"]), ("Vendég győzelem", imp["p2"])], key=lambda x: x[1])[0]
        else:
            sel = "Hazai győzelem"

        odds_est = _odds_for_selection(m, sel)
        risk, conf = _risk_conf_for_selection(m, sel)

        item = {
            "fixture_id": fid,
            "selection": sel,
            "is_highlighted": False,
            "confidence": conf,
            "risk_level": risk,
            "reason": "Feltöltő tipp (kevés meccs / kevés AI tipp) – odds/favorit alapján.",
            "odds_estimate": odds_est,
        }
        used.add(fid)
        if is_vip:
            vip.append(item)
        else:
            free.append(item)

    for _, m in candidates:
        if len(vip) < min_vip:
            add(m, True)
        elif len(free) < min_free:
            add(m, False)
        if len(vip) >= min_vip and len(free) >= min_free:
            break

    vip = _enforce_highlights(vip)[:MAX_VIP]
    free = free[:MAX_FREE]
    for t in free:
        t["is_highlighted"] = False
    return vip, free


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not matches:
        return {"telegram_public_text": "Ma nincs meccs.", "telegram_vip_text": "Ma nincs meccs.", "public_bets": [], "vip_bets": []}

    matches_norm = _matches_for_llm(matches)
    id_to_match: Dict[int, Dict[str, Any]] = {m["fixture_id"]: m for m in matches_norm if m.get("fixture_id") is not None}

    # shortlist: csak ahol van odds
    shortlist: List[Dict[str, Any]] = []
    for m in matches_norm:
        imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        if not imp:
            continue
        shortlist.append(
            {
                "fixture_id": m["fixture_id"],
                "league": m["league"],
                "country": m["country"],
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "kickoff": m["kickoff"],
                "odds_1": m["odds_1"],
                "odds_x": m["odds_x"],
                "odds_2": m["odds_2"],
                "p1": round(imp["p1"], 4),
                "px": round(imp["px"], 4),
                "p2": round(imp["p2"], 4),
            }
        )
    shortlist = shortlist[:40]

    free_raw: List[Dict[str, Any]] = []
    vip_raw: List[Dict[str, Any]] = []
    try:
        data = _call_llm(shortlist) if shortlist else {"free_tips": [], "vip_tips": []}
        free_raw = data.get("free_tips") or []
        vip_raw = data.get("vip_tips") or []
    except Exception as e:
        print("OpenAI hiba:", repr(e))

    vip = _clean_and_override(vip_raw, id_to_match)
    free = _clean_and_override(free_raw, id_to_match)

    vip, free = _fallback_fill(matches_norm, vip, free)

    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = (os.getenv("TIPPMIX_SLOT", "DAY") or "DAY").upper()
    slot_note = (os.getenv("TIPPMIX_SLOT_NOTE", "") or "").strip()
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"
    if slot_note:
        slot_text += f" – {slot_note}"

    vip_lines = [
        "🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI 🔥",
        f"Dátum: {today}",
        f"Idősáv: {slot_text}",
        f"Tippek száma: {len(vip)}",
        "────────────────────",
    ]

    ordered_v = sorted(vip, key=lambda t: (not t["is_highlighted"], -float(t["confidence"])))
    for idx, t in enumerate(ordered_v, 1):
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m) if m else f"Fixture ID={t['fixture_id']}"
        odds_txt = f"{t['odds_estimate']:.2f}" if t.get("odds_estimate") else "n/a"
        prefix = "💎 KIEMELT – " if t["is_highlighted"] else ""
        vip_lines.append(
            f"{idx}. {prefix}{label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason']}"
        )

    free_lines = [
        "👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK",
        f"Dátum: {today}",
        f"Idősáv: {slot_text}",
        "Ezek a mai, óvatosabb FREE tippek:",
        "────────────────────",
    ]

    ordered_f = sorted(free, key=lambda t: -float(t["confidence"]))
    for idx, t in enumerate(ordered_f, 1):
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m) if m else f"Fixture ID={t['fixture_id']}"
        odds_txt = f"{t['odds_estimate']:.2f}" if t.get("odds_estimate") else "n/a"
        free_lines.append(
            f"{idx}. {label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason']}"
        )

    vip_bets = [{"fixture_id": t["fixture_id"], "match": _build_match_label(id_to_match.get(t["fixture_id"], {})), "tip": t["selection"]} for t in vip]
    public_bets = [{"fixture_id": t["fixture_id"], "match": _build_match_label(id_to_match.get(t["fixture_id"], {})), "tip": t["selection"]} for t in free]

    return {
        "telegram_public_text": "\n\n".join(free_lines),
        "telegram_vip_text": "\n\n".join(vip_lines),
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
