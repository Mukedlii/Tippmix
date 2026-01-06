import os
import json
import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

client = OpenAI()

# ==============================
# Kötelező minimumok (fizetős bot)
# ==============================
DEFAULT_MIN_VIP = 6
DEFAULT_MIN_FREE = 3

# Maximumok (Telegram hossz / olvashatóság miatt)
MAX_VIP = 7
MAX_FREE = 5

SYSTEM_PROMPT = """
Te a Szelvénykirály sportfogadási AI vagy. Feladatod, hogy focimeccsekre az 1X2 piacon adj tippeket FREE és VIP csatornára.

KIMENETI SZABÁLYOK (nagyon szigorú):
- Csak három kimenet:
  * "Hazai győzelem"
  * "Döntetlen"
  * "Vendég győzelem"
- TILOS minden más piac.
- A JSON-on kívül SEMMIT nem írhatsz.

Cél: short-term találati arány javítása (inkább favoritok, döntetlen csak kivételesen).
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
                "required": [
                    "fixture_id",
                    "selection",
                    "is_highlighted",
                    "confidence",
                    "risk_level",
                    "reason",
                    "odds_estimate",
                ],
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
                "required": [
                    "fixture_id",
                    "selection",
                    "is_highlighted",
                    "confidence",
                    "risk_level",
                    "reason",
                    "odds_estimate",
                ],
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


def _implied_probs(o1: Optional[float], ox: Optional[float], o2: Optional[float]) -> Optional[Dict[str, float]]:
    if not o1 or not ox or not o2:
        return None
    if o1 <= 1.01 or ox <= 1.01 or o2 <= 1.01:
        return None
    p1, px, p2 = 1.0 / o1, 1.0 / ox, 1.0 / o2
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


def _default_risk_and_conf(p_top: float, edge: float) -> Tuple[str, float]:
    if p_top >= 0.60 and edge >= 0.10:
        risk = "alacsony"
    elif p_top >= 0.54 and edge >= 0.07:
        risk = "közepes"
    else:
        risk = "magas"
    conf = 1.0 + 8.0 * (p_top - 0.33) + 5.0 * edge
    conf = max(1.0, min(5.0, conf))
    return risk, conf


def _prefilter(matches_norm: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Lazább shortlist, hogy legyen miből dolgozni.
    """
    out: List[Dict[str, Any]] = []
    for m in matches_norm:
        imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        if not imp:
            continue

        # túl nagy overround = zajos piac
        if imp["overround"] > 0.20:
            continue

        fav, p_top, edge = _market_favorite(imp)

        # döntetlen ritkán
        if fav == "Döntetlen" and not (p_top >= 0.34 and edge >= 0.08):
            continue

        mm = dict(m)
        mm["implied"] = imp
        mm["market_favorite"] = fav
        mm["market_p_top"] = float(p_top)
        mm["market_edge"] = float(edge)
        out.append(mm)

    out.sort(key=lambda x: (x["market_p_top"], x["market_edge"]), reverse=True)
    return out[:40]


def _should_use_responses(model_name: str) -> bool:
    env = (os.getenv("TIPPMIX_USE_RESPONSES", "") or "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    return model_name.startswith("gpt-5")


def _call_openai_shortlist(shortlist: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = os.getenv("TIPPMIX_SLOT", "DAY").upper()
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    model_name = os.getenv("TIPPMIX_MODEL", "gpt-4.1-mini")
    reasoning_effort = os.getenv("TIPPMIX_REASONING_EFFORT", "low")
    verbosity = os.getenv("TIPPMIX_VERBOSITY", "low")

    # minimum igények (fizetős bot)
    min_vip = int(os.getenv("TIPPMIX_MIN_VIP", str(DEFAULT_MIN_VIP)))
    min_free = int(os.getenv("TIPPMIX_MIN_FREE", str(DEFAULT_MIN_FREE)))

    payload = []
    for m in shortlist:
        imp = m.get("implied") or {}
        payload.append(
            {
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
                "overround": round(float(imp.get("overround") or 0.0), 4),
            }
        )

    user_prompt = (
        f"Mai dátum: {today}\n"
        f"Idősáv: {slot_text}\n\n"
        "Shortlist (odds + implied prob alapján).\n"
        f"FONTOS: a bot fizetős, ezért legalább {min_free} FREE és legalább {min_vip} VIP tipp KELL.\n"
        "VIP-ben pontosan 3 legyen KIEMELT.\n"
        "Preferáld a piaci favoritot. Döntetlen ritkán.\n"
        "Kizárólag JSON-t adj vissza.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
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
        content = getattr(resp, "output_text", "") or ""
    else:
        temp = float(os.getenv("TIPPMIX_TEMP", "0.25"))
        r = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
            temperature=temp,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "tippmix_tips", "schema": TIPS_SCHEMA, "strict": True},
            },
        )
        content = r.choices[0].message.content or ""

    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("JSON root is not object")
    return data


def _call_openai_with_fallback(shortlist: List[Dict[str, Any]]) -> Dict[str, Any]:
    primary = os.getenv("TIPPMIX_MODEL", "gpt-4.1-mini")
    fallback = os.getenv("TIPPMIX_FALLBACK_MODEL", "gpt-4.1-mini")

    try:
        return _call_openai_shortlist(shortlist)
    except Exception as e:
        msg = str(e).lower()
        retryable = any(
            x in msg
            for x in [
                "model",
                "not found",
                "insufficient",
                "permission",
                "rate limit",
                "quota",
                "429",
                "403",
                "404",
                "503",
                "timeout",
                "overloaded",
            ]
        )
        print(f"[OpenAI] Primary failed: {primary} | {repr(e)}")
        if (not retryable) or (primary == fallback):
            raise
        print(f"[OpenAI] Falling back to: {fallback}")
        os.environ["TIPPMIX_MODEL"] = fallback
        try:
            return _call_openai_shortlist(shortlist)
        finally:
            os.environ["TIPPMIX_MODEL"] = primary


def _build_match_label(m: Dict[str, Any]) -> str:
    league_country = m["league"]
    if m.get("country"):
        league_country += f" {m['country']}"
    return f"{m['home_team']} vs {m['away_team']} ({league_country}, {m['kickoff']})"


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


def _clean_list(raw_list: List[Dict[str, Any]], id_to_match: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    allowed = {"Hazai győzelem", "Döntetlen", "Vendég győzelem"}
    out: List[Dict[str, Any]] = []
    for item in raw_list or []:
        try:
            fid = int(item.get("fixture_id"))
        except Exception:
            continue
        if fid not in id_to_match:
            continue
        sel = (item.get("selection") or "").strip()
        if sel not in allowed:
            continue
        out.append(
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
    return out


def _enforce_vip_highlights(vips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    v = sorted(vips, key=lambda t: float(t.get("confidence") or 0.0), reverse=True)
    for t in v:
        t["is_highlighted"] = False
    for t in v[:3]:
        t["is_highlighted"] = True
    return v


def _odds_based_pick(m: Dict[str, Any]) -> Tuple[str, Optional[float], float, float]:
    """
    Ha van odds: piaci favorit.
    Ha nincs odds: default Hazai győzelem (nagyon konzervatív fallback).
    Vissza: (selection, odds_est, p_top, edge)
    """
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    if not imp:
        return "Hazai győzelem", None, 0.50, 0.05  # nincs odds -> közepes, nem túl magabiztos
    fav, p_top, edge = _market_favorite(imp)
    odds_est = None
    if fav == "Hazai győzelem":
        odds_est = _safe_float(m.get("odds_1"))
    elif fav == "Döntetlen":
        odds_est = _safe_float(m.get("odds_x"))
    else:
        odds_est = _safe_float(m.get("odds_2"))
    return fav, odds_est, float(p_top), float(edge)


def _fill_minimum_tips(
    matches_norm: List[Dict[str, Any]],
    shortlist: List[Dict[str, Any]],
    id_to_match: Dict[int, Dict[str, Any]],
    vip_tips: List[Dict[str, Any]],
    free_tips: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    GARANCIA: VIP min 6, FREE min 3 (env-ből felülírható).
    Először shortlistből tölt fel, ha az kevés, akkor a teljes meccslistából.
    """
    min_vip = int(os.getenv("TIPPMIX_MIN_VIP", str(DEFAULT_MIN_VIP)))
    min_free = int(os.getenv("TIPPMIX_MIN_FREE", str(DEFAULT_MIN_FREE)))

    used = {t["fixture_id"] for t in vip_tips + free_tips}

    def add_pick(fid: int, sel: str, odds_est: Optional[float], p_top: float, edge: float, is_vip: bool):
        risk, conf = _default_risk_and_conf(p_top, edge)
        reason = f"Piaci/odds alapú választás (p={p_top:.2f}, edge={edge:.2f})."
        if odds_est is None:
            reason = "Nincs odds adat, konzervatív alap tipp a bot folytonossága miatt."

        item = {
            "fixture_id": fid,
            "selection": sel,
            "is_highlighted": False,
            "confidence": conf,
            "risk_level": risk if odds_est is not None else "közepes",
            "reason": reason,
            "odds_estimate": odds_est,
        }
        if is_vip:
            vip_tips.append(item)
        else:
            free_tips.append(item)

    # 1) shortlistből töltés
    candidates: List[Dict[str, Any]] = []
    candidates.extend(shortlist)

    # 2) ha kevés, egész listából is (norm)
    #    (itt “norm” elemek: odds_x/y/z lehet None)
    if len(candidates) < 60:
        candidates.extend([m for m in matches_norm if m.get("fixture_id") is not None])

    for m in candidates:
        fid = m.get("fixture_id")
        if not fid or fid in used or fid not in id_to_match:
            continue

        sel, odds_est, p_top, edge = _odds_based_pick(id_to_match[fid])

        # VIP-t töltjük először
        if len(vip_tips) < min_vip:
            add_pick(fid, sel, odds_est, p_top, edge, is_vip=True)
            used.add(fid)
            continue

        # utána FREE-t
        if len(free_tips) < min_free:
            add_pick(fid, sel, odds_est, p_top, edge, is_vip=False)
            used.add(fid)
            continue

        if len(vip_tips) >= min_vip and len(free_tips) >= min_free:
            break

    # limit + highlight
    vip_tips = vip_tips[:MAX_VIP]
    free_tips = free_tips[:MAX_FREE]
    vip_tips = _enforce_vip_highlights(vip_tips)
    for t in free_tips:
        t["is_highlighted"] = False

    return vip_tips, free_tips


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

    shortlist = _prefilter(matches_norm)

    free_raw: List[Dict[str, Any]] = []
    vip_raw: List[Dict[str, Any]] = []

    # AI próbál
    try:
        if shortlist:
            ai_data = _call_openai_with_fallback(shortlist)
        else:
            ai_data = {"free_tips": [], "vip_tips": []}
        free_raw = ai_data.get("free_tips") or []
        vip_raw = ai_data.get("vip_tips") or []
    except Exception as e:
        print("OpenAI hiba:", repr(e))

    vip_tips = _clean_list(vip_raw, id_to_match)
    free_tips = _clean_list(free_raw, id_to_match)

    # GARANCIA: mindig legyen minimum
    vip_tips, free_tips = _fill_minimum_tips(matches_norm, shortlist, id_to_match, vip_tips, free_tips)

    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = os.getenv("TIPPMIX_SLOT", "DAY").upper()
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    # VIP TELEGRAM
    vip_lines: List[str] = []
    vip_lines.append("🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI 🔥")
    vip_lines.append(f"Dátum: {today}")
    vip_lines.append(f"Idősáv: {slot_text}")
    vip_lines.append(f"Tippek száma: {len(vip_tips)}")
    vip_lines.append("────────────────────")

    ordered = sorted(vip_tips, key=lambda t: (not t["is_highlighted"], -t["confidence"]))
    for idx, tip in enumerate(ordered, start=1):
        m = id_to_match.get(tip["fixture_id"])
        match_label = _build_match_label(m) if m else f"Fixture ID={tip['fixture_id']}"
        highlight_prefix = "💎 KIEMELT – " if tip["is_highlighted"] else ""
        odds_txt = f"{tip['odds_estimate']:.2f}" if tip["odds_estimate"] else "n/a"
        vip_lines.append(
            f"{idx}. {highlight_prefix}{match_label}\n"
            f"🎯 Tipp: {tip['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(tip['risk_level'])}\n"
            f"💡 Bizalom: {_confidence_to_stars(tip['confidence'])}\n"
            f"🧠 Miért? {tip['reason'] or 'Statisztikai/odds alapú döntés.'}"
        )
    telegram_vip_text = "\n\n".join(vip_lines)

    # FREE TELEGRAM
    free_lines: List[str] = []
    free_lines.append("👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK")
    free_lines.append(f"Dátum: {today}")
    free_lines.append(f"Idősáv: {slot_text}")
    free_lines.append("Ezek a mai, óvatosabb FREE tippek:")
    free_lines.append("────────────────────")

    ordered_f = sorted(free_tips, key=lambda t: -t["confidence"])
    for idx, tip in enumerate(ordered_f, start=1):
        m = id_to_match.get(tip["fixture_id"])
        match_label = _build_match_label(m) if m else f"Fixture ID={tip['fixture_id']}"
        odds_txt = f"{tip['odds_estimate']:.2f}" if tip["odds_estimate"] else "n/a"
        free_lines.append(
            f"{idx}. {match_label}\n"
            f"🎯 Tipp: {tip['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(tip['risk_level'])}\n"
            f"💡 Bizalom: {_confidence_to_stars(tip['confidence'])}\n"
            f"🧠 Miért? {tip['reason'] or 'Óvatosabb statisztikai tipp.'}"
        )
    telegram_public_text = "\n\n".join(free_lines)

    # JSON mentéshez
    vip_bets = []
    for tip in vip_tips:
        m = id_to_match.get(tip["fixture_id"])
        vip_bets.append({"fixture_id": tip["fixture_id"], "match": _build_match_label(m) if m else "", "tip": tip["selection"]})

    public_bets = []
    for tip in free_tips:
        m = id_to_match.get(tip["fixture_id"])
        public_bets.append({"fixture_id": tip["fixture_id"], "match": _build_match_label(m) if m else "", "tip": tip["selection"]})

    return {
        "telegram_public_text": telegram_public_text,
        "telegram_vip_text": telegram_vip_text,
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
