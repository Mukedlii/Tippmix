import os
import json
import datetime
import random
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# --- Clients ---
gpt_client = OpenAI()  # OPENAI_API_KEY alapján

def _build_grok_client() -> Optional[OpenAI]:
    xai_key = os.getenv("XAI_API_KEY")
    if not xai_key:
        return None
    base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
    return OpenAI(api_key=xai_key, base_url=base_url)

grok_client = _build_grok_client()

# --- Config ---
MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))
MAX_VIP = int(os.getenv("TIPPMIX_MAX_VIP", "7"))
MAX_FREE = int(os.getenv("TIPPMIX_MAX_FREE", "5"))
STAKE_HUF = int(os.getenv("TIPPMIX_STAKE_HUF", "1000"))

ALLOWED = {"Hazai győzelem", "Döntetlen", "Vendég győzelem"}

USE_GROK_REVIEW = (os.getenv("TIPPMIX_USE_GROK_REVIEW", "1").strip().lower() in ("1", "true", "yes", "y"))

SYSTEM_PROMPT_GPT = """
Te egy profi futball-elemző vagy. 1X2 piacon adsz tippeket.

Elemzés:
- Hazai pálya, erőviszonyok, liga-szint (komoly vs egzotikus), tabella/forma/sérülés (ha van).
- Odds csak sanity check, nem vakon.

Szabály:
- Csak: "Hazai győzelem" | "Döntetlen" | "Vendég győzelem"
- VIP-ben pontosan 3 KIEMELT.
- VIP legalább 6 tipp, FREE legalább 3 tipp (ha a meccspool engedi).
- Ne add ugyanazt a meccset többször.
- Csak JSON-t adj vissza (se előtte, se utána szöveg).

Várt JSON séma:
{
  "vip_tips": [
    {"fixture_id": 123, "selection": "...", "confidence": 1-5, "risk_level": "alacsony|közepes|magas", "reason": "...", "is_highlighted": true|false}
  ],
  "free_tips": [
    {"fixture_id": 123, "selection": "...", "confidence": 1-5, "risk_level": "alacsony|közepes|magas", "reason": "..."}
  ]
}
""".strip()

SYSTEM_PROMPT_GROK = """
Te egy másodvélemény “reviewer” vagy.

Feladat:
- Ugyanazokat a meccs-dossziékat és a GPT által javasolt tippeket kapod.
- A cél: hibák kiszűrése (rossz favorit, túl rizikós döntetlen stb.), következetesebb kockázat/bizalom.
- MINDIG tartsd meg a fixture_id-k listáját. (Nem adhatsz hozzá újat.)
- Ha változtatsz, röviden indokold.

Szabály:
- Csak: "Hazai győzelem" | "Döntetlen" | "Vendég győzelem"
- risk_level csak: "alacsony" | "közepes" | "magas"
- confidence 1.0–5.0

Visszaadás: CSAK JSON (se előtte, se utána).
Várt JSON:
{
  "vip_review": [
    {"fixture_id": 123, "selection": "...", "confidence": 1-5, "risk_level": "...", "reason": "...", "verdict": "agree|change"}
  ],
  "free_review": [
    {"fixture_id": 123, "selection": "...", "confidence": 1-5, "risk_level": "...", "reason": "...", "verdict": "agree|change"}
  ]
}
""".strip()


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
    form = m.get("form") or {}
    injuries = m.get("injuries") or []
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

        "standings_home": (standings.get("home") or {}),
        "standings_away": (standings.get("away") or {}),
        "home_last5": (form.get("home_last5") or {}),
        "away_last5": (form.get("away_last5") or {}),
        "injuries_count": len(injuries),
        "injuries_sample": injuries[:6],
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


def _prob_for_selection(m: Dict[str, Any], sel: str) -> Optional[float]:
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    if not imp:
        return None
    if sel == "Hazai győzelem":
        return imp["p1"]
    if sel == "Döntetlen":
        return imp["px"]
    return imp["p2"]


def _baseline_pick(m: Dict[str, Any]) -> str:
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    if imp:
        items = [("Hazai győzelem", imp["p1"]), ("Döntetlen", imp["px"]), ("Vendég győzelem", imp["p2"])]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[0][0]

    r = random.random()
    if r < 0.62:
        return "Hazai győzelem"
    if r < 0.82:
        return "Vendég győzelem"
    return "Döntetlen"


def _baseline_risk_conf(m: Dict[str, Any], sel: str) -> Tuple[str, float]:
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    if not imp:
        return "közepes", 3.0

    p = imp["p1"] if sel == "Hazai győzelem" else (imp["px"] if sel == "Döntetlen" else imp["p2"])
    conf = 2.2 + 7.0 * (p - 0.33)
    conf = max(1.0, min(5.0, conf))

    if p >= 0.60:
        risk = "alacsony"
    elif p >= 0.52:
        risk = "közepes"
    else:
        risk = "magas"

    return risk, conf


def _parse_json_strict(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        # Utolsó mentsvár: kivágjuk az első { ... } blokkot
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except Exception:
                return {}
        return {}


def _call_gpt(dossiers: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = (os.getenv("TIPPMIX_SLOT", "DAY") or "DAY").upper()
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    model = os.getenv("TIPPMIX_MODEL", "gpt-5-mini")
    temp = float(os.getenv("TIPPMIX_TEMP", "0.25"))

    prompt = (
        f"Dátum: {today}\n"
        f"Idősáv: {slot_text}\n"
        f"Kötelező: VIP>={MIN_VIP}, FREE>={MIN_FREE}, VIP-ben pontosan 3 kiemelt.\n"
        "Kérlek ne add ugyanazt a meccset többször.\n"
        "A tippek legyenek vegyesek (ne csak hazai), ha a dosszié alapján indokolt.\n\n"
        "Meccs dossziék:\n"
        + json.dumps(dossiers, ensure_ascii=False, indent=2)
    )

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_GPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    # gpt-5* esetén ne küldj temperature-t (nálad már bevált)
    if not str(model).startswith("gpt-5"):
        kwargs["temperature"] = temp

    r = gpt_client.chat.completions.create(**kwargs)
    return _parse_json_strict(r.choices[0].message.content or "")


def _call_grok_review(dossiers: List[Dict[str, Any]], gpt_out: Dict[str, Any]) -> Dict[str, Any]:
    if not grok_client:
        return {}
    if not USE_GROK_REVIEW:
        return {}

    grok_model = os.getenv("TIPPMIX_GROK_MODEL", "grok-4")
    grok_temp = float(os.getenv("TIPPMIX_GROK_TEMP", "0.2"))

    prompt = (
        "Meccs dossziék (azonosak a GPT-vel):\n"
        + json.dumps(dossiers, ensure_ascii=False, indent=2)
        + "\n\nGPT tippek (ezeket review-zd):\n"
        + json.dumps(gpt_out, ensure_ascii=False, indent=2)
    )

    kwargs: Dict[str, Any] = {
        "model": grok_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_GROK},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": grok_temp,
    }

    r = grok_client.chat.completions.create(**kwargs)
    return _parse_json_strict(r.choices[0].message.content or "")


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


def _enforce_highlights(vip: List[Dict[str, Any]]) -> None:
    vip.sort(key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
    for t in vip:
        t["is_highlighted"] = False
    for t in vip[:3]:
        t["is_highlighted"] = True


def _clean_list(raw: List[Dict[str, Any]], id_to_match: Dict[int, Dict[str, Any]], used: set) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in raw or []:
        try:
            fid = int(it.get("fixture_id"))
        except Exception:
            continue
        if fid not in id_to_match:
            continue
        if fid in used:
            continue

        sel = (it.get("selection") or "").strip()
        if sel not in ALLOWED:
            continue

        m = id_to_match[fid]
        base_risk, base_conf = _baseline_risk_conf(m, sel)

        conf = _safe_float(it.get("confidence"))
        if conf is None:
            conf = base_conf
        conf = max(1.0, min(5.0, conf))

        risk = (it.get("risk_level") or base_risk).lower().strip()
        if risk not in ("alacsony", "közepes", "magas"):
            risk = base_risk

        reason = (it.get("reason") or "").strip()[:220] or "Összkép alapján."

        used.add(fid)
        out.append(
            {
                "fixture_id": fid,
                "selection": sel,
                "is_highlighted": bool(it.get("is_highlighted", False)),
                "confidence": conf,
                "risk_level": risk,
                "reason": reason,
                "odds_estimate": _odds_for_selection(m, sel),

                # audit mezők (későbbi stathoz)
                "gpt_selection": sel,
                "grok_selection": None,
                "consensus": "gpt_only",
            }
        )
    return out


def _apply_grok_review(
    tips: List[Dict[str, Any]],
    review: List[Dict[str, Any]],
    id_to_match: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    review_map: Dict[int, Dict[str, Any]] = {}
    for r in (review or []):
        try:
            fid = int(r.get("fixture_id"))
        except Exception:
            continue
        review_map[fid] = r

    for t in tips:
        fid = t["fixture_id"]
        r = review_map.get(fid)
        if not r:
            continue

        grok_sel = (r.get("selection") or "").strip()
        grok_verdict = (r.get("verdict") or "").strip().lower()

        if grok_sel in ALLOWED:
            t["grok_selection"] = grok_sel

        m = id_to_match.get(fid)
        gpt_sel = t["selection"]
        if not m or not t.get("grok_selection"):
            continue

        grok_sel = t["grok_selection"]

        # Ha egyetértenek: átlagolunk bizalmat, és oké
        if grok_sel == gpt_sel or grok_verdict == "agree":
            t["consensus"] = "agree"
            g_conf = _safe_float(r.get("confidence"))
            if g_conf is not None:
                t["confidence"] = max(1.0, min(5.0, (t["confidence"] + g_conf) / 2.0))
            # risk: maradhat, vagy finoman igazítjuk
            g_risk = (r.get("risk_level") or "").strip().lower()
            if g_risk in ("alacsony", "közepes", "magas"):
                t["risk_level"] = g_risk
            # reason: hozzáfűzzük röviden
            g_reason = (r.get("reason") or "").strip()
            if g_reason:
                t["reason"] = (t["reason"][:160] + f" | Grok: {g_reason[:160]}")[:220]
            t["odds_estimate"] = _odds_for_selection(m, t["selection"])
            continue

        # Ha nem értenek egyet: odds-sanity-check alapján döntünk
        p_gpt = _prob_for_selection(m, gpt_sel)
        p_grok = _prob_for_selection(m, grok_sel)

        chosen = gpt_sel
        if p_gpt is not None and p_grok is not None:
            # ha Grok javára érzékelhetően jobb az implied prob, átállunk
            if (p_grok - p_gpt) >= 0.06:
                chosen = grok_sel
            else:
                chosen = gpt_sel
        else:
            # ha nincs odds, marad a GPT (de bizalmat csökkentjük)
            chosen = gpt_sel

        if chosen == grok_sel:
            t["selection"] = grok_sel
            t["consensus"] = "grok_override"
        else:
            t["consensus"] = "gpt_override"

        # Disagreement penalty (kicsit visszavesszük a conf-ot)
        t["confidence"] = max(1.0, min(5.0, t["confidence"] - 0.4))

        g_risk = (r.get("risk_level") or "").strip().lower()
        if g_risk in ("alacsony", "közepes", "magas"):
            t["risk_level"] = g_risk

        g_reason = (r.get("reason") or "").strip()
        if g_reason:
            t["reason"] = (t["reason"][:150] + f" | Grok: {g_reason[:150]}")[:220]

        t["odds_estimate"] = _odds_for_selection(m, t["selection"])

    return tips


def _fill_minimum(matches_norm: List[Dict[str, Any]], vip: List[Dict[str, Any]], free: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    used = {t["fixture_id"] for t in vip + free}

    def has_full_odds(m: Dict[str, Any]) -> int:
        return 1 if (m.get("odds_1") and m.get("odds_x") and m.get("odds_2")) else 0

    pool = sorted(matches_norm, key=has_full_odds, reverse=True)

    def add_one(target: List[Dict[str, Any]]) -> bool:
        for m in pool:
            fid = m["fixture_id"]
            if fid in used:
                continue
            sel = _baseline_pick(m)
            risk, conf = _baseline_risk_conf(m, sel)
            target.append(
                {
                    "fixture_id": fid,
                    "selection": sel,
                    "is_highlighted": False,
                    "confidence": conf,
                    "risk_level": risk,
                    "reason": "Feltöltés: kevés AI tipp, a legjobb elérhető meccsekből.",
                    "odds_estimate": _odds_for_selection(m, sel),

                    "gpt_selection": sel,
                    "grok_selection": None,
                    "consensus": "fill",
                }
            )
            used.add(fid)
            return True
        return False

    while len(vip) < MIN_VIP:
        if not add_one(vip):
            break

    while len(free) < MIN_FREE:
        if not add_one(free):
            break

    vip = vip[:MAX_VIP]
    free = free[:MAX_FREE]

    for t in free:
        t["is_highlighted"] = False

    _enforce_highlights(vip)
    return vip, free


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not matches:
        msg = "⚠️ Ma nem jött vissza meccs az API-ból. Nézd meg a SPORTS_API_KEY-t / limitet."
        return {
            "telegram_public_text": msg,
            "telegram_vip_text": msg,
            "public_bets": [],
            "vip_bets": [],
        }

    matches_norm = [_normalize_match(m) for m in matches]
    id_to_match = {m["fixture_id"]: m for m in matches_norm}

    dossiers = matches_norm[:60]

    gpt_out: Dict[str, Any] = {}
    free_raw: List[Dict[str, Any]] = []
    vip_raw: List[Dict[str, Any]] = []
    try:
        gpt_out = _call_gpt(dossiers)
        free_raw = gpt_out.get("free_tips") or []
        vip_raw = gpt_out.get("vip_tips") or []
    except Exception as e:
        print("GPT/OpenAI hiba:", repr(e))

    used: set = set()
    vip = _clean_list(vip_raw, id_to_match, used)
    free = _clean_list(free_raw, id_to_match, used)

    # Grok review (opcionális, de nálad default ON)
    try:
        if grok_client and USE_GROK_REVIEW and gpt_out:
            grok_out = _call_grok_review(dossiers, gpt_out)
            vip = _apply_grok_review(vip, grok_out.get("vip_review") or [], id_to_match)
            free = _apply_grok_review(free, grok_out.get("free_review") or [], id_to_match)
    except Exception as e:
        print("Grok review hiba:", repr(e))

    vip, free = _fill_minimum(matches_norm, vip, free)

    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot = (os.getenv("TIPPMIX_SLOT", "DAY") or "DAY").upper()
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    vip_lines = [
        "🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI 🔥",
        f"Dátum: {today}.",
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

        # apró audit sor (nem kötelező, de hasznos)
        audit = ""
        if t.get("grok_selection"):
            audit = f"\n🧾 GPT: {t.get('gpt_selection')} | Grok: {t.get('grok_selection')} | ✅ {t.get('consensus')}"

        vip_lines.append(
            f"{i}. {prefix}{label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"💰 Várható kifizetés: {_payout_text(odds_val)}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason']}"
            f"{audit}"
        )

    free_lines = [
        "👑 SZELVÉNYKIRÁLY FREE – NAPI TIPPEK",
        f"Dátum: {today}.",
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

    # JSON mentéshez: bővebb mezők (statisztikához nagyon jó lesz)
    vip_bets = []
    for t in vip:
        m = id_to_match[t["fixture_id"]]
        vip_bets.append(
            {
                "fixture_id": t["fixture_id"],
                "match": _build_match_label(m),
                "tip": t["selection"],
                "odds": t.get("odds_estimate"),
                "confidence": t.get("confidence"),
                "risk_level": t.get("risk_level"),
                "is_highlighted": t.get("is_highlighted"),
                "gpt_tip": t.get("gpt_selection"),
                "grok_tip": t.get("grok_selection"),
                "consensus": t.get("consensus"),
            }
        )

    public_bets = []
    for t in free:
        m = id_to_match[t["fixture_id"]]
        public_bets.append(
            {
                "fixture_id": t["fixture_id"],
                "match": _build_match_label(m),
                "tip": t["selection"],
                "odds": t.get("odds_estimate"),
                "confidence": t.get("confidence"),
                "risk_level": t.get("risk_level"),
                "gpt_tip": t.get("gpt_selection"),
                "grok_tip": t.get("grok_selection"),
                "consensus": t.get("consensus"),
            }
        )

    return {
        "telegram_public_text": "\n\n".join(free_lines),
        "telegram_vip_text": "\n\n".join(vip_lines),
        "public_bets": public_bets,
        "vip_bets": vip_bets,
    }
