import os
import json
import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

client = OpenAI()

MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))
MAX_VIP = 7
MAX_FREE = 5
STAKE_HUF = int(os.getenv("TIPPMIX_STAKE_HUF", "1000"))

ALLOWED = {"Hazai győzelem", "Döntetlen", "Vendég győzelem"}

SYSTEM_PROMPT = """
Te egy profi futball-elemző vagy. 1X2 piacon adsz tippeket.

Döntési elvek:
- Ne csak az oddsot nézd: tabella/helyezés, forma (ha van), sérülések/hiányzók (ha van), hazai pálya.
- Odds csak sanity check, nem vakon.

Szabályok:
- Csak: "Hazai győzelem" | "Döntetlen" | "Vendég győzelem"
- VIP-ben pontosan 3 KIEMELT.
- FREE >= 3, VIP >= 6 (ha kevés meccs van a listában, akkor a legjobb elérhetőkből dolgozz).
- Csak JSON-t adj vissza.
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
                    "selection": {"type": "string", "enum": list(ALLOWED)},
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
                    "selection": {"type": "string", "enum": list(ALLOWED)},
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


def _normalize_match(m: Dict[str, Any]) -> Dict[str, Any]:
    odds = m.get("odds") or {}
    standings = m.get("standings") or {}
    injuries = m.get("injuries") or []

    def _team_st(team_key: str) -> Dict[str, Any]:
        st = standings.get(team_key) or {}
        return {
            "rank": st.get("rank"),
            "points": st.get("points"),
            "goalsDiff": st.get("goalsDiff"),
            "form": st.get("form"),
        }

    # injuries: rövidített összegzés
    inj_home = [x for x in injuries if (x.get("team") or "").lower().strip() == (m.get("home_team") or "").lower().strip()]
    inj_away = [x for x in injuries if (x.get("team") or "").lower().strip() == (m.get("away_team") or "").lower().strip()]

    return {
        "fixture_id": int(m["fixture_id"]),
        "league": m.get("league_name") or "",
        "country": m.get("country_name") or "",
        "kickoff": m.get("kickoff_local") or "",
        "home_team": m.get("home_team") or "",
        "away_team": m.get("away_team") or "",

        # odds (csak tájékoztató, de valódi)
        "odds_1": _safe_float(odds.get("1")),
        "odds_x": _safe_float(odds.get("X")),
        "odds_2": _safe_float(odds.get("2")),

        # tabella (ha van)
        "standings_home": _team_st("home"),
        "standings_away": _team_st("away"),

        # sérülés/hiányzó röviden
        "injuries_home_count": len(inj_home),
        "injuries_away_count": len(inj_away),
        "injuries_sample": [
            {"player": x.get("player"), "team": x.get("team"), "reason": x.get("reason")}
            for x in injuries[:6]
        ],
    }


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


def _odds_for_selection(m: Dict[str, Any], sel: str) -> Optional[float]:
    if sel == "Hazai győzelem":
        return _safe_float(m.get("odds_1"))
    if sel == "Döntetlen":
        return _safe_float(m.get("odds_x"))
    return _safe_float(m.get("odds_2"))


def _baseline_risk_conf(m: Dict[str, Any], sel: str) -> Tuple[str, float]:
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    if not imp:
        # nincs odds -> közepes baseline
        return "közepes", 3.1

    p = imp["p1"] if sel == "Hazai győzelem" else (imp["px"] if sel == "Döntetlen" else imp["p2"])

    # Profi baseline: p=0.33 ~ 2.3, p=0.50 ~ 3.5, p=0.60 ~ 4.2
    conf = 2.3 + 7.0 * (p - 0.33)
    conf = max(1.0, min(5.0, conf))

    if p >= 0.60:
        risk = "alacsony"
    elif p >= 0.52:
        risk = "közepes"
    else:
        risk = "magas"

    return risk, conf


def _should_use_responses() -> bool:
    v = (os.getenv("TIPPMIX_USE_RESPONSES", "1") or "").strip().lower()
    return v in ("1", "true", "yes")


def _call_llm(dossiers: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        f"Kötelező: VIP>={MIN_VIP}, FREE>={MIN_FREE}, VIP-ben pontosan 3 kiemelt.\n"
        "A döntéshez használd a dossziékat. Adj rövid, konkrét indokot (max 2-3 mondat).\n\n"
        "Dossziék:\n"
        + json.dumps(dossiers, ensure_ascii=False, indent=2)
    )

    if _should_use_responses() and hasattr(client, "responses"):
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
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        temperature=float(os.getenv("TIPPMIX_TEMP", "0.25")),
        response_format={"type": "json_schema", "json_schema": {"name": "tippmix_tips", "schema": SCHEMA, "strict": True}},
    )
    return json.loads(r.choices[0].message.content or "{}")


def _enforce_highlights(vip: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    vip_sorted = sorted(vip, key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
    for t in vip_sorted:
        t["is_highlighted"] = False
    for t in vip_sorted[:3]:
        t["is_highlighted"] = True
    return vip_sorted


def _clean_and_harden(raw: List[Dict[str, Any]], id_to_match: Dict[int, Dict[str, Any]], used_ids: set) -> List[Dict[str, Any]]:
    """
    Profi “hardening”:
    - selection valid
    - fixture id létezik
    - AI confidence csak finomhangolhat (baseline-hoz képest korlát)
    - odds_estimate mindig VALÓDI odds, AI-tól nem fogadjuk el
    - duplikált fixture kizárva
    """
    out: List[Dict[str, Any]] = []
    for it in raw or []:
        try:
            fid = int(it.get("fixture_id"))
        except Exception:
            continue
        if fid not in id_to_match:
            continue
        if fid in used_ids:
            continue

        sel = (it.get("selection") or "").strip()
        if sel not in ALLOWED:
            continue

        m = id_to_match[fid]
        base_risk, base_conf = _baseline_risk_conf(m, sel)

        ai_conf = _safe_float(it.get("confidence"))
        if ai_conf is None:
            conf = base_conf
        else:
            # AI csak +/-0.7-et térhet el a baseline-tól (profi stabilitás)
            conf = max(1.0, min(5.0, base_conf + max(-0.7, min(0.7, ai_conf - 3.0))))

        risk = (it.get("risk_level") or base_risk).lower().strip()
        if risk not in ("alacsony", "közepes", "magas"):
            risk = base_risk

        odds_val = _odds_for_selection(m, sel)  # csak valós odds
        reason = (it.get("reason") or "").strip()[:220]
        if not reason:
            reason = "Dosszié + összkép alapján."

        used_ids.add(fid)
        out.append(
            {
                "fixture_id": fid,
                "selection": sel,
                "is_highlighted": bool(it.get("is_highlighted", False)),
                "confidence": conf,
                "risk_level": risk,
                "reason": reason,
                "odds_estimate": odds_val,
            }
        )
    return out


def _fill_minimum_from_pool(matches_norm: List[Dict[str, Any]], vip: List[Dict[str, Any]], free: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Profi feltöltés: külön meccsekből egészíti ki a listát.
    (Ha a poolban sincs elég, akkor ennyit tud – de SportAPI-val normálisan van elég.)
    """
    used = {t["fixture_id"] for t in vip + free}

    # rangsor: ahol van odds + van standings info -> előre
    def score(m: Dict[str, Any]) -> Tuple[int, int]:
        has_odds = 1 if (m.get("odds_1") and m.get("odds_x") and m.get("odds_2")) else 0
        has_st = 1 if ((m.get("standings_home") or {}).get("rank") is not None and (m.get("standings_away") or {}).get("rank") is not None) else 0
        return (-has_odds, -has_st)

    pool = sorted(matches_norm, key=score)

    def favorite_sel(m: Dict[str, Any]) -> str:
        imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        if not imp:
            return "Hazai győzelem"
        items = [("Hazai győzelem", imp["p1"]), ("Döntetlen", imp["px"]), ("Vendég győzelem", imp["p2"])]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[0][0]

    def add(target: List[Dict[str, Any]], fid: int, sel: str):
        m = next((x for x in pool if x["fixture_id"] == fid), None)
        if not m:
            return
        risk, conf = _baseline_risk_conf(m, sel)
        target.append(
            {
                "fixture_id": fid,
                "selection": sel,
                "is_highlighted": False,
                "confidence": conf,
                "risk_level": risk,
                "reason": "Feltöltés: a legjobb elérhető meccsekből (odds/tabella alapján).",
                "odds_estimate": _odds_for_selection(m, sel),
            }
        )

    for m in pool:
        fid = m["fixture_id"]
        if len(vip) >= MIN_VIP:
            break
        if fid in used:
            continue
        add(vip, fid, favorite_sel(m))
        used.add(fid)

    for m in pool:
        fid = m["fixture_id"]
        if len(free) >= MIN_FREE:
            break
        if fid in used:
            continue
        add(free, fid, favorite_sel(m))
        used.add(fid)

    vip = _enforce_highlights(vip)[:MAX_VIP]
    free = free[:MAX_FREE]
    for t in free:
        t["is_highlighted"] = False
    return vip, free


def _risk_to_emoji(r: str) -> str:
    r = (r or "").lower()
    if "alacsony" in r:
        return "🟢 alacsony"
    if "magas" in r:
        return "🔴 magas"
    return "🟠 közepes"


def _stars(conf: float) -> str:
    c = max(1.0, min(5.0, float(conf)))
    return "⭐" * int(round(c)) + f" ({c:.1f}/5)"


def _build_match_label(m: Dict[str, Any]) -> str:
    league_country = m.get("league") or ""
    if m.get("country"):
        league_country += f" {m['country']}"
    return f"{m.get('home_team')} vs {m.get('away_team')} ({league_country}, {m.get('kickoff')})"


def _payout_text(odds_val: Optional[float]) -> str:
    if not odds_val:
        return "n/a"
    win = int(round(STAKE_HUF * float(odds_val)))
    prof = win - STAKE_HUF
    return f"{win:,} Ft (profit: {prof:,} Ft)".replace(",", " ")


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

    # csak az első 40 dosszié az AI-nak (token + gyorsaság)
    dossiers = matches_norm[:40]

    free_raw: List[Dict[str, Any]] = []
    vip_raw: List[Dict[str, Any]] = []
    try:
        data = _call_llm(dossiers)
        free_raw = data.get("free_tips") or []
        vip_raw = data.get("vip_tips") or []
    except Exception as e:
        print("OpenAI hiba:", repr(e))

    used_ids: set = set()
    vip = _clean_and_harden(vip_raw, id_to_match, used_ids)
    free = _clean_and_harden(free_raw, id_to_match, used_ids)

    vip, free = _fill_minimum_from_pool(matches_norm, vip, free)

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
        f"💵 Tét példa: {STAKE_HUF} Ft / tipp",
        "────────────────────",
    ]
    for i, t in enumerate(vip, 1):
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m)
        odds_val = t.get("odds_estimate")
        odds_txt = f"{odds_val:.2f}" if odds_val else "n/a"
        prefix = "💎 KIEMELT – " if t.get("is_highlighted") else ""
        vip_lines.append(
            f"{i}. {prefix}{label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"💰 Várható kifizetés: {_payout_text(odds_val)}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason']}"
        )

    free_lines = [
        "👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK",
        f"Dátum: {today}",
        f"Idősáv: {slot_text}",
        f"💵 Tét példa: {STAKE_HUF} Ft / tipp",
        "────────────────────",
    ]
    for i, t in enumerate(free, 1):
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m)
        odds_val = t.get("odds_estimate")
        odds_txt = f"{odds_val:.2f}" if odds_val else "n/a"
        free_lines.append(
            f"{i}. {label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"💰 Várható kifizetés: {_payout_text(odds_val)}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason']}"
        )

    vip_bets = [{"fixture_id": t["fixture_id"], "match": _build_match_label(id_to_match[t["fixture_id"]]), "tip": t["selection"]} for t in vip]
    public_bets = [{"fixture_id": t["fixture_id"], "match": _build_match_label(id_to_match[t["fixture_id"]]), "tip": t["selection"]} for t in free]

    return {
        "telegram_public_text": "\n\n".join(free_lines),
        "telegram_vip_text": "\n\n".join(vip_lines),
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
