import os
import json
import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

client = OpenAI()

MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))

SYSTEM_PROMPT = """
Te egy profi futball-elemző vagy.
Feladat: 1X2 piacon adj tippeket úgy, hogy a meccseket "dosszié" alapján elemzed:
- hazai pálya / idegenbeli forma
- tabella helyezés / pont / gólkülönbség (ha van)
- sérülések/hiányzók (különösen kulcsjátékosok)
- odds csak sanity check, nem vakon

KIMENET:
- csak három selection lehet:
  "Hazai győzelem" | "Döntetlen" | "Vendég győzelem"
- visszaadás: JSON, free_tips és vip_tips
- VIP-ben pont 3 kiemelt (is_highlighted=true)
- FREE legalább 3, VIP legalább 6 (ha kevés meccs, akkor is válassz a listából)
"""

SCHEMA = {
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
                "required": ["fixture_id","selection","is_highlighted","confidence","risk_level","reason","odds_estimate"],
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
                "required": ["fixture_id","selection","is_highlighted","confidence","risk_level","reason","odds_estimate"],
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


def _normalize_match(m: Dict[str, Any]) -> Dict[str, Any]:
    odds = m.get("odds") or {}
    return {
        "fixture_id": int(m["fixture_id"]),
        "league": m.get("league_name") or "",
        "country": m.get("country_name") or "",
        "kickoff": m.get("kickoff_local") or "",
        "home_team": m.get("home_team") or "",
        "away_team": m.get("away_team") or "",
        "odds_1": _safe_float(odds.get("1")),
        "odds_x": _safe_float(odds.get("X")),
        "odds_2": _safe_float(odds.get("2")),
        "standings": m.get("standings"),
        "injuries": m.get("injuries"),
        # ha football-data fallback nyers standings benne van, átadjuk:
        "standings_fallback": m.get("standings_fallback"),
    }


def _call_llm(matches_norm: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = (os.getenv("TIPPMIX_SLOT", "DAY") or "DAY").upper()
    slot_note = (os.getenv("TIPPMIX_SLOT_NOTE", "") or "").strip()

    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"
    if slot_note:
        slot_text += f" – {slot_note}"

    model = os.getenv("TIPPMIX_MODEL", "gpt-5-mini")

    prompt = (
        f"Dátum: {today}\n"
        f"Idősáv: {slot_text}\n"
        f"Kötelező minimum: FREE>={MIN_FREE}, VIP>={MIN_VIP}\n"
        "VIP-ben pontosan 3 legyen kiemelt.\n\n"
        "Meccs dossziék (JSON lista):\n"
        + json.dumps(matches_norm, ensure_ascii=False, indent=2)
    )

    use_responses = (os.getenv("TIPPMIX_USE_RESPONSES", "1").lower() in ("1","true","yes"))
    if use_responses and hasattr(client, "responses"):
        resp = client.responses.create(
            model=model,
            reasoning={"effort": os.getenv("TIPPMIX_REASONING_EFFORT", "low")},
            instructions=SYSTEM_PROMPT,
            input=[{"role": "user", "content": prompt}],
            text={
                "verbosity": os.getenv("TIPPMIX_VERBOSITY", "low"),
                "format": {"type": "json_schema", "name": "tippmix_tips", "schema": SCHEMA, "strict": True},
            },
        )
        return json.loads(resp.output_text or "{}")

    r = client.chat.completions.create(
        model=model,
        messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}],
        temperature=float(os.getenv("TIPPMIX_TEMP","0.25")),
        response_format={"type":"json_schema","json_schema":{"name":"tippmix_tips","schema":SCHEMA,"strict":True}},
    )
    return json.loads(r.choices[0].message.content or "{}")


def _risk_to_emoji(r: str) -> str:
    r = (r or "").lower()
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
    league_country = m.get("league") or ""
    if m.get("country"):
        league_country += f" {m['country']}"
    return f"{m.get('home_team')} vs {m.get('away_team')} ({league_country}, {m.get('kickoff')})"


def _clean_list(raw: List[Dict[str, Any]], id_to_match: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    allowed = {"Hazai győzelem","Döntetlen","Vendég győzelem"}
    out = []
    seen = set()
    for it in raw or []:
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
        seen.add(fid)
        out.append({
            "fixture_id": fid,
            "selection": sel,
            "is_highlighted": bool(it.get("is_highlighted", False)),
            "confidence": float(it.get("confidence") or 3.5),
            "risk_level": (it.get("risk_level") or "közepes").lower(),
            "reason": (it.get("reason") or "").strip(),
            "odds_estimate": _safe_float(it.get("odds_estimate")),
        })
    return out


def _force_counts(matches_norm: List[Dict[str, Any]], vip: List[Dict[str, Any]], free: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Garantálja a minimumot úgy, hogy mindig külön meccs legyen.
    Ha kevés a meccs a poolban, akkor amennyit tud, kitölt (de SportAPI poolnál normálisan lesz elég).
    """
    used = {t["fixture_id"] for t in vip + free}
    all_ids = [m["fixture_id"] for m in matches_norm if m.get("fixture_id") is not None]

    # egyszerű feltöltés: ami kimaradt, arra a piaci favorit (ha van odds), különben hazai
    def favorite(m: Dict[str, Any]) -> str:
        o1, ox, o2 = m.get("odds_1"), m.get("odds_x"), m.get("odds_2")
        # min odds = favorit
        pairs = []
        if o1: pairs.append(("Hazai győzelem", o1))
        if ox: pairs.append(("Döntetlen", ox))
        if o2: pairs.append(("Vendég győzelem", o2))
        if not pairs:
            return "Hazai győzelem"
        pairs.sort(key=lambda x: x[1])
        return pairs[0][0]

    def add_to(target: List[Dict[str, Any]], fid: int, sel: str):
        target.append({
            "fixture_id": fid,
            "selection": sel,
            "is_highlighted": False,
            "confidence": 3.2,
            "risk_level": "közepes",
            "reason": "Feltöltés: kevés tipp érkezett, piaci favorit / alap logika alapján.",
            "odds_estimate": None,
        })

    # VIP
    for fid in all_ids:
        if len(vip) >= MIN_VIP:
            break
        if fid in used:
            continue
        m = next((x for x in matches_norm if x["fixture_id"] == fid), None)
        if not m:
            continue
        add_to(vip, fid, favorite(m))
        used.add(fid)

    # FREE
    for fid in all_ids:
        if len(free) >= MIN_FREE:
            break
        if fid in used:
            continue
        m = next((x for x in matches_norm if x["fixture_id"] == fid), None)
        if not m:
            continue
        add_to(free, fid, favorite(m))
        used.add(fid)

    # pontosan 3 kiemelt VIP-ben
    vip_sorted = sorted(vip, key=lambda x: float(x.get("confidence") or 0), reverse=True)
    for t in vip_sorted:
        t["is_highlighted"] = False
    for t in vip_sorted[:3]:
        t["is_highlighted"] = True

    return vip_sorted, free


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not matches:
        return {
            "telegram_public_text": "Ma sajnos nem találtam érdemi FREE tippet.",
            "telegram_vip_text": "Ma sajnos nem találtam érdemi VIP tippet.",
            "public_bets": [],
            "vip_bets": [],
        }

    matches_norm = [_normalize_match(m) for m in matches]
    id_to_match = {m["fixture_id"]: m for m in matches_norm}

    # csak az első ~40 dossziét adjuk az AI-nak (a többi fallback kitöltéshez)
    llm_input = matches_norm[:40]

    try:
        data = _call_llm(llm_input)
        free_raw = data.get("free_tips") or []
        vip_raw = data.get("vip_tips") or []
    except Exception as e:
        print("OpenAI hiba:", repr(e))
        free_raw, vip_raw = [], []

    vip = _clean_list(vip_raw, id_to_match)
    free = _clean_list(free_raw, id_to_match)

    # minimum kitöltés
    vip, free = _force_counts(matches_norm, vip, free)

    # Telegram szöveg
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
    for i, t in enumerate(vip, 1):
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m)
        odds_txt = f"{t['odds_estimate']:.2f}" if t.get("odds_estimate") else "n/a"
        prefix = "💎 KIEMELT – " if t.get("is_highlighted") else ""
        vip_lines.append(
            f"{i}. {prefix}{label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason'] or 'Dosszié-alapú elemzés alapján.'}"
        )

    free_lines = [
        "👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK",
        f"Dátum: {today}",
        f"Idősáv: {slot_text}",
        "Ezek a mai, óvatosabb FREE tippek:",
        "────────────────────",
    ]
    for i, t in enumerate(free, 1):
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m)
        odds_txt = f"{t['odds_estimate']:.2f}" if t.get("odds_estimate") else "n/a"
        free_lines.append(
            f"{i}. {label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason'] or 'Dosszié-alapú elemzés alapján.'}"
        )

    vip_bets = [{"fixture_id": t["fixture_id"], "match": _build_match_label(id_to_match[t["fixture_id"]]), "tip": t["selection"]} for t in vip]
    public_bets = [{"fixture_id": t["fixture_id"], "match": _build_match_label(id_to_match[t["fixture_id"]]), "tip": t["selection"]} for t in free]

    return {
        "telegram_public_text": "\n\n".join(free_lines),
        "telegram_vip_text": "\n\n".join(vip_lines),
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
