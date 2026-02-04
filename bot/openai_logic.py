# bot/openai_logic.py
import os
import json
import datetime
import random
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

client = OpenAI()

MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))

# Ha nem akarsz plafont, állítsd env-ben nagyobbra.
MAX_VIP = int(os.getenv("TIPPMIX_MAX_VIP", str(MIN_VIP)))
MAX_FREE = int(os.getenv("TIPPMIX_MAX_FREE", str(MIN_FREE)))

STAKE_HUF = int(os.getenv("TIPPMIX_STAKE_HUF", "1000"))

# "Perfect 6-fold" profile (tunable via env)
# Defaults tuned for a 6-fold total odds target ~10–15 (geo mean ~1.47–1.57)
VIP_ODDS_MIN = float(os.getenv("TIPPMIX_VIP_ODDS_MIN", "1.35"))
VIP_ODDS_MAX = float(os.getenv("TIPPMIX_VIP_ODDS_MAX", "1.85"))
VIP_HIGH_ODDS_THRESHOLD = float(os.getenv("TIPPMIX_VIP_HIGH_ODDS_THRESHOLD", "1.75"))
VIP_MAX_HIGH_ODDS = int(os.getenv("TIPPMIX_VIP_MAX_HIGH_ODDS", "2"))
VIP_REQUIRE_ODDS = (os.getenv("TIPPMIX_VIP_REQUIRE_ODDS") or "1").strip() == "1"

# Defaults tuned for a 4-fold free combo total odds ~6–10 (geo mean ~1.57–1.78)
FREE_ODDS_MIN = float(os.getenv("TIPPMIX_FREE_ODDS_MIN", "1.40"))
FREE_ODDS_MAX = float(os.getenv("TIPPMIX_FREE_ODDS_MAX", "2.10"))
FREE_REQUIRE_ODDS = (os.getenv("TIPPMIX_FREE_REQUIRE_ODDS") or "0").strip() == "1"

# VIP bonus combo (printed in VIP message, not counted in the 6 mandatory VIP tips)
VIP_BONUS_COUNT = int(os.getenv("TIPPMIX_VIP_BONUS_COUNT", "4"))
VIP_BONUS_ODDS_MIN = float(os.getenv("TIPPMIX_VIP_BONUS_ODDS_MIN", "1.70"))
VIP_BONUS_ODDS_MAX = float(os.getenv("TIPPMIX_VIP_BONUS_ODDS_MAX", "2.60"))
VIP_BONUS_HIGH_ODDS_THRESHOLD = float(os.getenv("TIPPMIX_VIP_BONUS_HIGH_ODDS_THRESHOLD", "2.30"))
VIP_BONUS_MAX_HIGH_ODDS = int(os.getenv("TIPPMIX_VIP_BONUS_MAX_HIGH_ODDS", "2"))

ALLOWED = {"Hazai győzelem", "Döntetlen", "Vendég győzelem"}

SYSTEM_PROMPT = """
Te egy profi futball-elemző vagy. 1X2 piacon adsz tippeket.

Cél: "stabil" 6-os VIP kombi (magasabb találati arány), ezért kerüld a coinflip (2.30+) tippeket.

Elemzés:
- Hazai pálya, erőviszonyok, liga-szint (komoly vs egzotikus), tabella/forma/sérülés (ha van).
- Odds csak sanity check, nem vakon.

Szabály:
- Csak: "Hazai győzelem" | "Döntetlen" | "Vendég győzelem"
- VIP-ben pontosan 3 KIEMELT.
- VIP legalább 6 tipp, FREE legalább 3 tipp (ha a meccspool engedi).
- Ne add ugyanazt a meccset többször.
- Csak JSON-t adj vissza (se előtte, se utána szöveg).
Kimenet példa:
{
  "vip_tips":[{"fixture_id":123,"selection":"Hazai győzelem","confidence":4.3,"risk_level":"közepes","reason":"...","is_highlighted":true}, ...],
  "free_tips":[{"fixture_id":456,"selection":"Vendég győzelem","confidence":3.8,"risk_level":"magas","reason":"..."}, ...]
}
"""

VALIDATOR_SYSTEM_PROMPT = """
Te egy szigorú sportfogadási QA (minőségellenőr) vagy.
Feladat: a javasolt tipplista tisztítása.

Szabályok:
- Ne legyen túl sok döntetlen (VIP max 1, FREE max 1).
- Friendlies csak akkor maradhat, ha (odds <= 1.60) ÉS (confidence >= 4.2).
- Egzotikus ligák: ha odds>2.20 és confidence<4.0, inkább cseréld/eldobod.

- VIP 6-os kombi stabilitás:
  - VIP-ben preferáld az odds {VIP_ODDS_MIN:.2f}–{VIP_ODDS_MAX:.2f} tartományt.
  - VIP-ben max {VIP_MAX_HIGH_ODDS} tipp lehet {VIP_HIGH_ODDS_THRESHOLD:.2f} felett.

- Ne legyen duplikált fixture.
- VIP: legalább 6 tipp, pontosan 3 kiemelt.
- FREE: legalább 3 tipp.
- Csak a megadott fixture_id-k közül válassz.

Kimenet: csak JSON, mezők:
{
  "vip_tips":[...],
  "free_tips":[...],
  "notes":"rövid megjegyzés"
}
"""

# LLM nélküli döntetlen-vágás
MAX_DRAWS_VIP = int(os.getenv("TIPPMIX_MAX_DRAWS_VIP", "1"))
MAX_DRAWS_FREE = int(os.getenv("TIPPMIX_MAX_DRAWS_FREE", "1"))


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


def _call_llm(dossiers: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        f"Odds-szabály (stabilabb 6-os kombi):\n"
        f"- VIP odds tartomány: {VIP_ODDS_MIN:.2f}–{VIP_ODDS_MAX:.2f} (cél: 6-os kombi ~10–15 össz-odds)\n"
        f"- VIP max {VIP_MAX_HIGH_ODDS} tipp lehet {VIP_HIGH_ODDS_THRESHOLD:.2f} felett\n"
        f"- FREE odds tartomány: {FREE_ODDS_MIN:.2f}–{FREE_ODDS_MAX:.2f} (cél: 4-es kombi ~6–10 össz-odds)\n\n"
        "Meccs dossziék:\n"
        + json.dumps(dossiers, ensure_ascii=False, indent=2)
    )

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    # gpt-5* esetén NE küldj temperature-t
    if not str(model).startswith("gpt-5"):
        kwargs["temperature"] = temp

    r = client.chat.completions.create(**kwargs)
    return json.loads(r.choices[0].message.content or "{}")


def _call_validator(dossiers: List[Dict[str, Any]], vip_raw: List[Dict[str, Any]], free_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    model = os.getenv("TIPPMIX_VALIDATOR_MODEL") or os.getenv("TIPPMIX_MODEL", "gpt-5-mini")
    temp = float(os.getenv("TIPPMIX_TEMP", "0.25"))

    allowed_ids = [d.get("fixture_id") for d in dossiers if d.get("fixture_id") is not None]

    prompt_obj = {
        "allowed_fixture_ids": allowed_ids,
        "vip_tips_proposed": vip_raw,
        "free_tips_proposed": free_raw,
        "constraints": {
            "min_vip": MIN_VIP,
            "min_free": MIN_FREE,
            "vip_exact_highlights": 3,
            "max_draws_vip": MAX_DRAWS_VIP,
            "max_draws_free": MAX_DRAWS_FREE,
        },
        "note": "Csak a megadott allowed_fixture_ids listából válassz. Csak 1X2. Csak JSON.",
    }

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt_obj, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
    }

    if not str(model).startswith("gpt-5"):
        kwargs["temperature"] = temp

    r = client.chat.completions.create(**kwargs)
    return json.loads(r.choices[0].message.content or "{}")


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
    """Pick exactly 3 highlighted tips.

    Prefer tips that have odds (more "pro" feel), then higher confidence.
    """

    def has_odds(x: Dict[str, Any]) -> int:
        try:
            return 1 if float(x.get("odds_estimate") or 0) > 0 else 0
        except Exception:
            return 0

    vip.sort(
        key=lambda x: (
            has_odds(x),
            float(x.get("confidence") or 0.0),
        ),
        reverse=True,
    )

    for t in vip:
        t["is_highlighted"] = False
    for t in vip[:3]:
        t["is_highlighted"] = True


def _odds_ok(odds_val: Optional[float], tier: str) -> bool:
    if odds_val is None:
        return not (VIP_REQUIRE_ODDS if tier == "VIP" else FREE_REQUIRE_ODDS)
    if tier == "VIP":
        return VIP_ODDS_MIN <= float(odds_val) <= VIP_ODDS_MAX
    return FREE_ODDS_MIN <= float(odds_val) <= FREE_ODDS_MAX


def _clean_list(raw: List[Dict[str, Any]], id_to_match: Dict[int, Dict[str, Any]], used: set, tier: str) -> List[Dict[str, Any]]:
    tier = (tier or "").upper()
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
        odds_val = _odds_for_selection(m, sel)
        if not _odds_ok(odds_val, tier=tier):
            continue

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
                "odds_estimate": odds_val,
            }
        )
    return out


def _cap_draws(tips: List[Dict[str, Any]], max_draws: int) -> List[Dict[str, Any]]:
    if max_draws < 0:
        return tips
    out: List[Dict[str, Any]] = []
    draws = 0
    for t in tips:
        if t.get("selection") == "Döntetlen":
            if draws >= max_draws:
                continue
            draws += 1
        out.append(t)
    return out


def _best_sel_within(m: Dict[str, Any], tier: str) -> Optional[str]:
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    # score selections by implied probability
    if imp:
        candidates = [
            ("Hazai győzelem", imp["p1"], _odds_for_selection(m, "Hazai győzelem")),
            ("Döntetlen", imp["px"], _odds_for_selection(m, "Döntetlen")),
            ("Vendég győzelem", imp["p2"], _odds_for_selection(m, "Vendég győzelem")),
        ]
        candidates = [c for c in candidates if _odds_ok(c[2], tier=tier)]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0] if candidates else None

    # fallback: use baseline pick if odds ok
    sel = _baseline_pick(m)
    return sel if _odds_ok(_odds_for_selection(m, sel), tier=tier) else None


def _odds_val(t: Dict[str, Any]) -> float:
    try:
        return float(t.get("odds_estimate") or 0)
    except Exception:
        return 0.0


def _enforce_vip_high_odds_cap(vip: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Drop tips above VIP_ODDS_MAX already handled by _odds_ok; now cap "high odds" count.
    highs = [t for t in vip if _odds_val(t) > VIP_HIGH_ODDS_THRESHOLD]
    if len(highs) <= VIP_MAX_HIGH_ODDS:
        return vip

    # remove the highest odds first
    highs_sorted = sorted(highs, key=_odds_val, reverse=True)
    to_remove = set(x["fixture_id"] for x in highs_sorted[VIP_MAX_HIGH_ODDS:])
    return [t for t in vip if t["fixture_id"] not in to_remove]


def _pick_bonus(matches_norm: List[Dict[str, Any]], used: set) -> List[Dict[str, Any]]:
    """Build an extra VIP bonus list (count=VIP_BONUS_COUNT) from remaining matches.

    Best-effort: prefers implied-probability highest selection that falls within bonus odds window.
    """

    if VIP_BONUS_COUNT <= 0:
        return []

    def odds_ok_bonus(odds_val: Optional[float]) -> bool:
        if odds_val is None:
            return False
        return VIP_BONUS_ODDS_MIN <= float(odds_val) <= VIP_BONUS_ODDS_MAX

    out: List[Dict[str, Any]] = []

    # build candidate tips
    candidates: List[Dict[str, Any]] = []
    for m in matches_norm:
        fid = m["fixture_id"]
        if fid in used:
            continue

        imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
        if not imp:
            continue

        options = [
            ("Hazai győzelem", imp["p1"], _odds_for_selection(m, "Hazai győzelem")),
            ("Döntetlen", imp["px"], _odds_for_selection(m, "Döntetlen")),
            ("Vendég győzelem", imp["p2"], _odds_for_selection(m, "Vendég győzelem")),
        ]
        options = [o for o in options if odds_ok_bonus(o[2])]
        if not options:
            continue
        options.sort(key=lambda x: x[1], reverse=True)
        sel, p, o = options[0]

        risk, conf = _baseline_risk_conf(m, sel)
        candidates.append(
            {
                "fixture_id": fid,
                "selection": sel,
                "is_highlighted": False,
                "confidence": conf,
                "risk_level": risk,
                "reason": "Bónusz kombi: odds-ablak + implied valószínűség alapján.",
                "odds_estimate": o,
                "_p": p,
            }
        )

    # sort by implied probability and confidence
    candidates.sort(key=lambda x: (float(x.get("_p") or 0.0), float(x.get("confidence") or 0.0)), reverse=True)

    # enforce high-odds cap for bonus
    high_count = 0
    for c in candidates:
        if len(out) >= VIP_BONUS_COUNT:
            break
        o = _odds_val(c)
        if o > VIP_BONUS_HIGH_ODDS_THRESHOLD:
            if high_count >= VIP_BONUS_MAX_HIGH_ODDS:
                continue
            high_count += 1

        used.add(c["fixture_id"])
        c.pop("_p", None)
        out.append(c)

    return out


def _fill_minimum(matches_norm: List[Dict[str, Any]], vip: List[Dict[str, Any]], free: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    used = {t["fixture_id"] for t in vip + free}

    def has_full_odds(m: Dict[str, Any]) -> int:
        return 1 if (m.get("odds_1") and m.get("odds_x") and m.get("odds_2")) else 0

    pool = sorted(matches_norm, key=has_full_odds, reverse=True)

    def add_one(target: List[Dict[str, Any]], tier: str) -> bool:
        for m in pool:
            fid = m["fixture_id"]
            if fid in used:
                continue
            sel = _best_sel_within(m, tier=tier)
            if not sel:
                continue
            odds_val = _odds_for_selection(m, sel)
            if not _odds_ok(odds_val, tier=tier):
                continue

            risk, conf = _baseline_risk_conf(m, sel)
            target.append(
                {
                    "fixture_id": fid,
                    "selection": sel,
                    "is_highlighted": False,
                    "confidence": conf,
                    "risk_level": risk,
                    "reason": "Feltöltés: kevés AI tipp, a legjobb elérhető meccsekből.",
                    "odds_estimate": odds_val,
                }
            )
            used.add(fid)
            return True
        return False

    # First, enforce VIP high-odds cap on the (possibly LLM-generated) list, then refill.
    vip = _enforce_vip_high_odds_cap(vip)

    while len(vip) < MIN_VIP:
        if not add_one(vip, tier="VIP"):
            break

    while len(free) < MIN_FREE:
        if not add_one(free, tier="FREE"):
            break

    # Döntetlen cap + utána újra feltöltés, hogy a minimumok biztosan meglegyenek
    vip = _cap_draws(vip, MAX_DRAWS_VIP)
    free = _cap_draws(free, MAX_DRAWS_FREE)

    # Re-apply VIP high-odds cap after draw trimming, then refill again.
    vip = _enforce_vip_high_odds_cap(vip)

    used2 = {t["fixture_id"] for t in vip + free}
    used.clear()
    used.update(used2)

    while len(vip) < MIN_VIP:
        if not add_one(vip, tier="VIP"):
            break
    while len(free) < MIN_FREE:
        if not add_one(free, tier="FREE"):
            break

    # NEM vágjuk kicsire agresszíven, de ha valaki beállította a MAX-ot, akkor érvényes.
    if MAX_VIP > 0:
        vip = vip[:MAX_VIP]
    if MAX_FREE > 0:
        free = free[:MAX_FREE]

    for t in free:
        t["is_highlighted"] = False

    _enforce_highlights(vip)
    return vip, free


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not matches:
        msg = "⚠️ Ma nem jött vissza meccs az API-ból. Nézd meg a SPORTS_API_KEY / SPORTSDATAIO_API kulcsot és a limitet."
        return {"telegram_public_text": msg, "telegram_vip_text": msg, "public_bets": [], "vip_bets": []}

    matches_norm = [_normalize_match(m) for m in matches]
    id_to_match = {m["fixture_id"]: m for m in matches_norm}

    dossiers = matches_norm[: int(os.getenv("TIPPMIX_DOSSIER_LIMIT", "60"))]

    free_raw: List[Dict[str, Any]] = []
    vip_raw: List[Dict[str, Any]] = []
    try:
        data = _call_llm(dossiers)
        free_raw = data.get("free_tips") or []
        vip_raw = data.get("vip_tips") or []
    except Exception as e:
        print("OpenAI hiba (primary):", repr(e))

    # Validator kör (opcionális)
    if os.getenv("TIPPMIX_USE_VALIDATOR", "1") == "1":
        try:
            v = _call_validator(dossiers, vip_raw, free_raw)
            vip_raw = v.get("vip_tips") or vip_raw
            free_raw = v.get("free_tips") or free_raw
        except Exception as e:
            print("OpenAI hiba (validator):", repr(e))

    used: set = set()
    vip = _clean_list(vip_raw, id_to_match, used, tier="VIP")
    free = _clean_list(free_raw, id_to_match, used, tier="FREE")

    vip, free = _fill_minimum(matches_norm, vip, free)

    # Final VIP cap enforcement (safety)
    vip = _enforce_vip_high_odds_cap(vip)

    # Build VIP bonus list from remaining matches (does not affect mandatory counts)
    used_bonus = set(t["fixture_id"] for t in vip + free)
    vip_bonus = _pick_bonus(matches_norm, used_bonus)

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
        vip_lines.append(
            f"{i}. {prefix}{label}\n"
            f"🎯 Tipp: {t['selection']}\n"
            f"📊 Odds (1X2): {odds_txt}\n"
            f"💰 Várható kifizetés: {_payout_text(odds_val)}\n"
            f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            f"💡 Bizalom: {_stars(t['confidence'])}\n"
            f"🧠 Miért? {t['reason']}"
        )

    if vip_bonus:
        vip_lines.append("────────────────────")
        vip_lines.append(f"🎁 VIP BONUS – {len(vip_bonus)} tipp (külön kombi)")
        for j, t in enumerate(vip_bonus, 1):
            m = id_to_match.get(t["fixture_id"])
            label = _build_match_label(m)
            odds_val = t.get("odds_estimate")
            odds_txt = f"{odds_val:.2f}" if odds_val else "n/a"
            vip_lines.append(
                f"B{j}. {label}\n"
                f"🎯 Tipp: {t['selection']}\n"
                f"📊 Odds (1X2): {odds_txt}\n"
                f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
                f"💡 Bizalom: {_stars(t['confidence'])}"
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

    # 1/B: kibővített mezők a JSON exporthoz
    vip_bets = [
        {
            "fixture_id": t["fixture_id"],
            "match": _build_match_label(id_to_match[t["fixture_id"]]),
            "tip": t["selection"],
            "odds": t.get("odds_estimate"),
            "confidence": t.get("confidence"),
            "risk_level": t.get("risk_level"),
            "is_highlighted": bool(t.get("is_highlighted")),
            "league": id_to_match[t["fixture_id"]].get("league"),
            "country": id_to_match[t["fixture_id"]].get("country"),
            "kickoff": id_to_match[t["fixture_id"]].get("kickoff"),
        }
        for t in vip
    ]

    public_bets = [
        {
            "fixture_id": t["fixture_id"],
            "match": _build_match_label(id_to_match[t["fixture_id"]]),
            "tip": t["selection"],
            "odds": t.get("odds_estimate"),
            "confidence": t.get("confidence"),
            "risk_level": t.get("risk_level"),
            "is_highlighted": False,
            "league": id_to_match[t["fixture_id"]].get("league"),
            "country": id_to_match[t["fixture_id"]].get("country"),
            "kickoff": id_to_match[t["fixture_id"]].get("kickoff"),
        }
        for t in free
    ]

    return {
        "telegram_public_text": "\n\n".join(free_lines),
        "telegram_vip_text": "\n\n".join(vip_lines),
        "public_bets": public_bets,
        "vip_bets": vip_bets,
        # Note: bonus is informational only (not stored/recapped by default)
        "vip_bonus_bets": [
            {
                "fixture_id": t["fixture_id"],
                "match": _build_match_label(id_to_match[t["fixture_id"]]),
                "tip": t["selection"],
                "odds": t.get("odds_estimate"),
                "confidence": t.get("confidence"),
                "risk_level": t.get("risk_level"),
                "is_highlighted": False,
                "league": id_to_match[t["fixture_id"]].get("league"),
                "country": id_to_match[t["fixture_id"]].get("country"),
                "kickoff": id_to_match[t["fixture_id"]].get("kickoff"),
                "is_bonus": True,
            }
            for t in (vip_bonus or [])
        ],
    }
