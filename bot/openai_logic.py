# bot/openai_logic.py
import os
import json
import datetime
import random
from typing import Any, Dict, List, Optional, Tuple


def _promo_footer(today_iso: str, lang: str) -> str:
    """7-day free promo footer.

    Env:
      - TIPPMIX_PROMO_ENABLED=1/0
      - TIPPMIX_PROMO_START=YYYY-MM-DD (default: today)
      - TIPPMIX_PROMO_DAYS=7
      - TIPPMIX_PRICE_USD=10
    """

    if (os.getenv("TIPPMIX_PROMO_ENABLED") or "1").strip() != "1":
        return ""

    start = (os.getenv("TIPPMIX_PROMO_START") or today_iso).strip() or today_iso
    try:
        days = int(os.getenv("TIPPMIX_PROMO_DAYS") or "7")
    except Exception:
        days = 7
    try:
        price = int(float(os.getenv("TIPPMIX_PRICE_USD") or "10"))
    except Exception:
        price = 10

    try:
        dt0 = datetime.date.fromisoformat(start)
        end = (dt0 + datetime.timedelta(days=max(1, days))).strftime("%Y.%m.%d.")
    except Exception:
        end = ""

    if (lang or "hu").lower().startswith("en"):
        end_txt = f" (until {end})" if end else ""
        return f"\n\n🎁 7-day FREE beta{end_txt} → then ${price}/month."

    end_txt = f" (eddig: {end})" if end else ""
    return f"\n\n🎁 7 nap INGYEN beta{end_txt} → utána ${price}/hó."

from openai import OpenAI

client = OpenAI()

MIN_VIP = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
MIN_FREE = int(os.getenv("TIPPMIX_MIN_FREE", "3"))

# Presentation / structuring
VIP_MAIN1_COUNT = int(os.getenv("TIPPMIX_VIP_MAIN1_COUNT", "6"))
VIP_MAIN2_COUNT = int(os.getenv("TIPPMIX_VIP_MAIN2_COUNT", "6"))
FREE_SAFE_COUNT = int(os.getenv("TIPPMIX_FREE_SAFE_COUNT", "3"))
FREE_RISKY_COUNT = int(os.getenv("TIPPMIX_FREE_RISKY_COUNT", "3"))
IMPORTANT_MIN = int(os.getenv("TIPPMIX_IMPORTANT_MIN", "6"))

# Ha nem akarsz plafont, állítsd env-ben nagyobbra.
MAX_VIP = int(os.getenv("TIPPMIX_MAX_VIP", str(MIN_VIP)))
MAX_FREE = int(os.getenv("TIPPMIX_MAX_FREE", str(MIN_FREE)))

STAKE_HUF = int(os.getenv("TIPPMIX_STAKE_HUF", "1000"))
# Display-only for EN channel
STAKE_USD = float(os.getenv("TIPPMIX_STAKE_USD", "5"))

# "Perfect 6-fold" profile (tunable via env)
# Defaults tuned for a 6-fold total odds target ~10–15 (geo mean ~1.47–1.57)
VIP_ODDS_MIN = float(os.getenv("TIPPMIX_VIP_ODDS_MIN", "1.35"))
VIP_ODDS_MAX = float(os.getenv("TIPPMIX_VIP_ODDS_MAX", "1.85"))
VIP_SAFE_MAX_FALLBACK = float(os.getenv("TIPPMIX_VIP_SAFE_MAX_FALLBACK", "1.95"))
VIP_HIGH_ODDS_THRESHOLD = float(os.getenv("TIPPMIX_VIP_HIGH_ODDS_THRESHOLD", "1.75"))
VIP_MAX_HIGH_ODDS = int(os.getenv("TIPPMIX_VIP_MAX_HIGH_ODDS", "2"))
VIP_REQUIRE_ODDS = (os.getenv("TIPPMIX_VIP_REQUIRE_ODDS") or "1").strip() == "1"

# If strict odds constraints produce too few VIP/FREE tips, allow an automatic relaxation pass.
RELAX_IF_SHORT = (os.getenv("TIPPMIX_RELAX_IF_SHORT") or "1").strip() == "1"
VIP_ODDS_MAX_RELAX = float(os.getenv("TIPPMIX_VIP_ODDS_MAX_RELAX", "2.20"))
FREE_ODDS_MAX_RELAX = float(os.getenv("TIPPMIX_FREE_ODDS_MAX_RELAX", "2.40"))


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
        "bucket": m.get("bucket"),
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


def _fmt_time(kickoff: str) -> str:
    """Telegram-friendly time formatter from ISO-like kickoff."""
    s = (kickoff or "").strip()
    if "T" in s:
        try:
            t = s.split("T", 1)[1]
            return t[:5]
        except Exception:
            return ""
    # fallback
    return s[:5]


def _league_line(m: Dict[str, Any]) -> str:
    league = (m.get("league") or "").strip()
    country = (m.get("country") or "").strip()
    if league and country:
        return f"🏆 Liga: {league} – {country}"
    if league:
        return f"🏆 Liga: {league}"
    return ""


def _build_match_label(m: Dict[str, Any]) -> str:
    """Short match label for blocks (no parentheses spam)."""
    return f"{m.get('home_team')} vs {m.get('away_team')}"


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


def _odds_ok(odds_val: Optional[float], tier: str, relax: bool = False) -> bool:
    if odds_val is None:
        if tier == "VIP":
            return (not VIP_REQUIRE_ODDS) or relax
        return (not FREE_REQUIRE_ODDS) or relax

    if tier == "VIP":
        mx = VIP_ODDS_MAX_RELAX if relax else VIP_ODDS_MAX
        return VIP_ODDS_MIN <= float(odds_val) <= mx

    mx = FREE_ODDS_MAX_RELAX if relax else FREE_ODDS_MAX
    return FREE_ODDS_MIN <= float(odds_val) <= mx


def _is_top_league(league: str) -> bool:
    s = (league or "").strip().lower()
    top = [
        "premier league",
        "la liga",
        "bundesliga",
        "serie a",
        "ligue 1",
        "championship",
        "eredivisie",
        "primeira liga",
        "uefa",
        "champions league",
        "europa league",
        "conference league",
        "world cup",
        "euro",
    ]
    return any(x in s for x in top)


def _shelf_for_tip(m: Dict[str, Any], odds_val: Optional[float], risk: str, conf: float, tier: str) -> str:
    """Assign a presentation shelf label.

    PRO should be genuinely selective (stronger leagues + safer + higher confidence).
    STANDARD is the main body.
    BOLD/MERÉSZ is handled separately.
    """

    try:
        bucket = int(m.get("bucket")) if m.get("bucket") is not None else 9
    except Exception:
        bucket = 9

    risk_l = (risk or "").lower()
    league = str(m.get("league") or "")

    # PRO gate: top bucket/top league + odds present + not high risk + stronger confidence.
    if (
        (bucket <= 1 or _is_top_league(league))
        and odds_val is not None
        and "magas" not in risk_l
        and float(conf or 0) >= 4.1
    ):
        return "PRO"

    return "STANDARD"


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
        if not _odds_ok(odds_val, tier=tier, relax=False):
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

        shelf = _shelf_for_tip(m, odds_val, risk=risk, conf=conf, tier=tier)

        out.append(
            {
                "fixture_id": fid,
                "selection": sel,
                "is_highlighted": bool(it.get("is_highlighted", False)),
                "confidence": conf,
                "risk_level": risk,
                "reason": reason,
                "odds_estimate": odds_val,
                "shelf": shelf,
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


def _best_sel_within(m: Dict[str, Any], tier: str, relax: bool = False) -> Optional[str]:
    imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
    # score selections by implied probability
    if imp:
        candidates = [
            ("Hazai győzelem", imp["p1"], _odds_for_selection(m, "Hazai győzelem")),
            ("Döntetlen", imp["px"], _odds_for_selection(m, "Döntetlen")),
            ("Vendég győzelem", imp["p2"], _odds_for_selection(m, "Vendég győzelem")),
        ]
        candidates = [c for c in candidates if _odds_ok(c[2], tier=tier, relax=relax)]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0] if candidates else None

    # fallback: use baseline pick if odds ok
    sel = _baseline_pick(m)
    return sel if _odds_ok(_odds_for_selection(m, sel), tier=tier, relax=relax) else None


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
                "reason": "Merész odds (opcionális).",
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

    def add_one(target: List[Dict[str, Any]], tier: str, relax: bool = False) -> bool:
        for m in pool:
            fid = m["fixture_id"]
            if fid in used:
                continue
            sel = _best_sel_within(m, tier=tier, relax=relax)
            if not sel:
                continue
            odds_val = _odds_for_selection(m, sel)
            if not _odds_ok(odds_val, tier=tier, relax=relax):
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
        if not add_one(vip, tier="VIP", relax=False):
            break

    while len(free) < MIN_FREE:
        if not add_one(free, tier="FREE", relax=False):
            break

    # If we are short, do a best-effort relaxation pass (keeps daily minimum counts).
    if RELAX_IF_SHORT:
        while len(vip) < MIN_VIP:
            if not add_one(vip, tier="VIP", relax=True):
                break
        while len(free) < MIN_FREE:
            if not add_one(free, tier="FREE", relax=True):
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
        provider = (os.getenv("SPORTS_DATA_PROVIDER") or "auto").strip()
        msg = (
            "⚠️ Ma nem jött vissza meccs az API-ból. "
            f"Provider: {provider}. "
            "Ellenőrizd a providerhez tartozó kulcsot + limitet: "
            "SPORTS_API_KEY (api-sports) / SPORTMONKS_API_TOKEN / ALLSPORTSAPI_KEY / SPORTSDATAIO_API. "
            "Ha rossz provider van beállítva: állítsd a GitHub Actions Variable-ben: SPORTS_DATA_PROVIDER=allsportsapi (vagy api-sports)."
        )
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
    slot_text_en = "Day" if slot == "DAY" else "Evening"

    def sel_en(sel: str) -> str:
        return {
            "Hazai győzelem": "Home win",
            "Döntetlen": "Draw",
            "Vendég győzelem": "Away win",
        }.get(sel, sel)

    def risk_en(r: str) -> str:
        r = (r or "").lower()
        if "alacsony" in r:
            return "Low"
        if "magas" in r:
            return "High"
        return "Medium"

    def _is_safe_vip(t: Dict[str, Any], max_odds: float) -> bool:
        """Define the pool used for combos.

        If odds are available, enforce VIP odds window.
        If odds are missing (common on AllSportsAPI/free tiers), still allow SAFE by risk+confidence,
        but payout won't be computed.
        """
        risk = (t.get("risk_level") or "").lower()
        if "magas" in risk:
            return False

        # If we have odds, validate window.
        odds_val = _safe_float(t.get("odds_estimate"))
        if odds_val and odds_val > 1.01:
            if odds_val > float(max_odds) or odds_val < VIP_ODDS_MIN:
                return False
            return True

        # No odds: allow only confident + low/medium risk tips into combos.
        conf = _safe_float(t.get("confidence")) or 0
        return conf >= 3.6

    safe_vip = [t for t in vip if _is_safe_vip(t, VIP_ODDS_MAX)]
    unsafe_vip = [t for t in vip if t not in safe_vip]

    # For combos, IMPORTANT is a subset (top picks). We only need enough SAFE picks for 2 combos.
    need_safe = max(0, VIP_MAIN1_COUNT) + max(0, VIP_MAIN2_COUNT)
    need_safe = max(need_safe, max(0, IMPORTANT_MIN))
    used_fallback = False
    if len(safe_vip) < need_safe and VIP_SAFE_MAX_FALLBACK > VIP_ODDS_MAX:
        safe2 = [t for t in vip if _is_safe_vip(t, VIP_SAFE_MAX_FALLBACK)]
        if len(safe2) > len(safe_vip):
            safe_vip = safe2
            unsafe_vip = [t for t in vip if t not in safe_vip]
            used_fallback = True

    # If still short, build SAFE fillers from the full match pool (odds-required).
    if len(safe_vip) < need_safe:
        used_ids = {int(t.get("fixture_id")) for t in (vip + free) if t.get("fixture_id") is not None}
        max_odds = VIP_SAFE_MAX_FALLBACK if used_fallback else VIP_ODDS_MAX

        # Prefer matches that have at least some odds (free-tier odds sources can be partial).
        def _has_any_odds(m: Dict[str, Any]) -> int:
            return 1 if (_safe_float(m.get("odds_1")) or _safe_float(m.get("odds_x")) or _safe_float(m.get("odds_2"))) else 0

        pool = sorted(matches_norm, key=_has_any_odds, reverse=True)

        for m in pool:
            if len(safe_vip) >= need_safe:
                break
            fid = int(m["fixture_id"])
            if fid in used_ids:
                continue

            sel = _best_sel_within(m, tier="VIP", relax=True)
            if not sel:
                continue
            odds_val = _odds_for_selection(m, sel)
            if odds_val is not None:
                if not (VIP_ODDS_MIN <= float(odds_val) <= float(max_odds)):
                    continue

            risk, conf = _baseline_risk_conf(m, sel)
            if (risk or "").lower() == "magas":
                continue
            # If we don't have odds, require a bit more confidence so combos stay "stable".
            if odds_val is None and float(conf or 0) < 3.6:
                continue

            safe_vip.append(
                {
                    "fixture_id": fid,
                    "selection": sel,
                    "is_highlighted": False,
                    "confidence": conf,
                    "risk_level": risk,
                    "reason": "Stabil odds + implied valószínűség alapján.",
                    "odds_estimate": odds_val,
                    "shelf": _shelf_for_tip(m, odds_val, risk=risk, conf=conf, tier="VIP"),
                }
            )
            used_ids.add(fid)

    # ---- structure: IMPORTANT + 2 combos + bold risky ----
    def _quality_key(t: Dict[str, Any]) -> tuple:
        m = id_to_match.get(int(t.get("fixture_id"))) or {}
        try:
            bucket = int(m.get("bucket")) if m.get("bucket") is not None else 9
        except Exception:
            bucket = 9
        league = str(m.get("league") or "")
        top = 1 if _is_top_league(league) else 0
        risk = (t.get("risk_level") or "").lower()
        risk_score = 2 if "alacsony" in risk else (1 if "közepes" in risk else 0)
        conf = float(t.get("confidence") or 0)
        odds_present = 1 if _safe_float(t.get("odds_estimate")) else 0
        # sort: better bucket, top league, odds present, risk, confidence
        return (-top, bucket, -odds_present, -risk_score, -conf)

    safe_vip.sort(key=_quality_key)

    important = safe_vip[: max(0, IMPORTANT_MIN)]

    def _has_odds_tip(t: Dict[str, Any]) -> bool:
        o = _safe_float(t.get("odds_estimate"))
        return bool(o and o > 1.01)

    def _combo_build(source: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
        """Prefer odds-present tips so we can compute 1000 Ft payout."""
        with_odds = [t for t in source if _has_odds_tip(t)]
        no_odds = [t for t in source if t not in with_odds]
        out = with_odds[:n]
        if len(out) < n:
            out += no_odds[: max(0, n - len(out))]
        return out

    # Build combos from SAFE pool, but prioritize tips with odds so we can show stake totals.
    main1 = _combo_build(safe_vip, max(0, VIP_MAIN1_COUNT))
    main2 = _combo_build(safe_vip[len(main1):], max(0, VIP_MAIN2_COUNT))

    def _build_combo_from_pool(
        n: int,
        used_ids: set,
        odds_min: float,
        odds_max: float,
    ) -> List[Dict[str, Any]]:
        """Hard combo-engine: build an odds-backed combo directly from the match pool.

        Goal: always produce N picks with odds so we can compute 1000 Ft payout.
        Selection is based on implied probability (from odds) and baseline risk/conf.
        """

        candidates = []
        for m in matches_norm:
            try:
                fid = int(m.get("fixture_id"))
            except Exception:
                continue
            if fid in used_ids:
                continue

            # Pick best selection based on implied probs & odds windows.
            sel = _best_sel_within(m, tier="VIP", relax=True)
            if not sel:
                continue

            o = _odds_for_selection(m, sel)
            if o is None:
                continue
            try:
                o = float(o)
            except Exception:
                continue
            if o <= 1.01:
                continue
            if o < float(odds_min) or o > float(odds_max):
                continue

            # implied probability
            imp = _implied_probs(m.get("odds_1"), m.get("odds_x"), m.get("odds_2"))
            if not imp:
                continue
            p = {
                "Hazai győzelem": imp.get("p1"),
                "Döntetlen": imp.get("px"),
                "Vendég győzelem": imp.get("p2"),
            }.get(sel)
            if p is None:
                continue

            risk, conf = _baseline_risk_conf(m, sel)
            if (risk or "").lower() == "magas":
                continue

            candidates.append((float(p), float(conf or 0), -float(o), fid, sel, o, risk, conf))

        # sort: highest implied prob, then confidence, then prefer lower odds a bit
        candidates.sort(reverse=True)

        out: List[Dict[str, Any]] = []
        for _, _, _, fid, sel, o, risk, conf in candidates:
            if len(out) >= n:
                break
            if fid in used_ids:
                continue
            out.append(
                {
                    "fixture_id": fid,
                    "selection": sel,
                    "is_highlighted": False,
                    "confidence": conf,
                    "risk_level": risk,
                    "reason": "KOMBI-ENGINE: implied valószínűség + stabil odds alapján.",
                    "odds_estimate": float(o),
                    "shelf": _shelf_for_tip(id_to_match.get(fid) or {}, float(o), risk=risk, conf=conf, tier="VIP"),
                }
            )
            used_ids.add(fid)

        return out

    # If combos are still short, force-fill them from the pool with odds-backed picks.
    try:
        want1 = max(0, VIP_MAIN1_COUNT)
        want2 = max(0, VIP_MAIN2_COUNT)
        used_combo_ids = {int(t.get("fixture_id")) for t in (vip + free + main1 + main2) if t.get("fixture_id") is not None}

        # Hard engine odds window (tunable)
        eng_min = float(os.getenv("TIPPMIX_COMBO_ENGINE_ODDS_MIN", str(VIP_ODDS_MIN)))
        eng_max = float(os.getenv("TIPPMIX_COMBO_ENGINE_ODDS_MAX", "2.40"))

        if len(main1) < want1:
            fill = _build_combo_from_pool(want1 - len(main1), used_combo_ids, eng_min, eng_max)
            main1 += fill

        if len(main2) < want2:
            fill = _build_combo_from_pool(want2 - len(main2), used_combo_ids, eng_min, eng_max)
            main2 += fill

    except Exception:
        pass

    vip_extra = safe_vip[max(0, VIP_MAIN1_COUNT + VIP_MAIN2_COUNT) :]

    # unsafe (red/high odds/high risk) gets pushed to the bold section
    vip_unsafe_extra = unsafe_vip

    vip_lines = [
        "👑⚽️ SZELVÉNYKIRÁLY VIP – NAPI AJÁNLÓ ⚽️👑",
        f"📅 Dátum: {today}",
        "🙂 3 polc: 🏆 PRO / 🧩 STANDARD / 😈 MERÉSZ",
    ]
    if used_fallback:
        vip_lines.append(f"⚠️ Ma kevés volt a SAFE meccs {VIP_ODDS_MAX:.2f} odds-ig, ezért kitágítottam {VIP_SAFE_MAX_FALLBACK:.2f}-ig a KOMBI-hoz.")

    vip_lines.append(f"✅ <b>FONTOS MECCSEK</b> (min. {IMPORTANT_MIN})")

    sep_en = "💎⚽️💎"

    vip_lines_en = [
        "👑⚽️ BETSLIPKING VIP – DAILY PICKS ⚽️👑",
        f"📅 Date: {today}.",
        "🙂 3 shelves: 🏆PRO / 🧩STANDARD / 😈BOLD",
    ]
    if used_fallback:
        vip_lines_en.append(f"⚠️ SAFE pool was short up to {VIP_ODDS_MAX:.2f}, so I widened to {VIP_SAFE_MAX_FALLBACK:.2f} for combos.")

    vip_lines_en.append(f"✅ IMPORTANT MATCHES (min {IMPORTANT_MIN})")

    def _shelf_hu(t: Dict[str, Any]) -> str:
        s = (t.get("shelf") or "").upper()
        if s == "PRO":
            return "🏆 PRO"
        if s == "STANDARD":
            return "🧩 STANDARD"
        if s == "BOLD":
            return "😈 MERESZ"
        return "🧩 STANDARD"

    def _shelf_en(t: Dict[str, Any]) -> str:
        s = (t.get("shelf") or "").upper()
        if s == "PRO":
            return "🏆 PRO"
        if s == "STANDARD":
            return "🧩 STANDARD"
        if s == "BOLD":
            return "😈 BOLD"
        return "🧩 STANDARD"

    def _append_tip_block(lines_hu: List[str], lines_en: List[str], idx: int, t: Dict[str, Any], label: str):
        odds_val = t.get("odds_estimate")
        odds_txt = f"{odds_val:.2f}" if odds_val else "n/a"
        prefix = "⭐ KIEMELT – " if t.get("is_highlighted") else ""

        reason = (t.get("reason") or "").strip()
        if reason.startswith("Feltöltés:"):
            reason = "Stabil odds + összkép alapján."
        if (t.get("shelf") or "").upper() == "BOLD":
            reason = ""

        m = id_to_match.get(int(t.get("fixture_id"))) if t.get("fixture_id") is not None else None
        m = m or {}
        league_line = _league_line(m)
        time_txt = _fmt_time(str(m.get("kickoff") or ""))

        block = (
            f"{idx}. {_shelf_hu(t)}  {prefix}{label}\n"
            + (f"{league_line}\n" if league_line else "")
            + (f"🕒 Idő: {time_txt}\n" if time_txt else "")
            + f"🎯 Tipp: {t['selection']}\n"
            + f"📊 Odds: {odds_txt}\n"
            + f"⚠️ Kockázat: {_risk_to_emoji(t['risk_level'])}\n"
            + f"💡 Bizalom: {_stars(t['confidence'])}"
        )
        if reason:
            block += f"\n🧠 Miért? {reason}"

        # Low-data note only when needed
        try:
            bucket = int(m.get("bucket")) if m.get("bucket") is not None else 9
        except Exception:
            bucket = 9
        if bucket >= 4 or (odds_txt == "n/a"):
            block += "\n⚠️ Adatbiztonság: alacsony"

        lines_hu.append(block)

        reason_en = (t.get("reason") or "").strip()
        if (t.get("shelf") or "").upper() == "BOLD":
            reason_en = ""

        block_en = (
            f"{idx}. {_shelf_en(t)}  {('⭐ HIGHLIGHT – ' if t.get('is_highlighted') else '')}{label}\n"
            f"Pick: {sel_en(t['selection'])}\n"
            f"Odds: {odds_txt}\n"
            f"Risk: {risk_en(t['risk_level'])}\n"
            f"Confidence: {t['confidence']:.1f}/5"
        )
        if reason_en:
            block_en += f"\nWhy? {reason_en}"
        lines_en.append(block_en)

    # IMPORTANT
    important_idx: Dict[Any, int] = {}
    for i, t in enumerate(important, 1):
        important_idx[t["fixture_id"]] = i
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m)
        _append_tip_block(vip_lines, vip_lines_en, i, t, label)

    def _combo_totals(tips: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[int], Optional[int]]:
        odds_vals: List[float] = []
        for t in tips:
            try:
                o = float(t.get("odds_estimate") or 0)
            except Exception:
                o = 0
            if o > 1.01:
                odds_vals.append(o)
        if len(odds_vals) != len(tips) or not odds_vals:
            return None, None, None
        total_odds = 1.0
        for o in odds_vals:
            total_odds *= float(o)
        payout = int(round(STAKE_HUF * total_odds))
        profit = payout - int(STAKE_HUF)
        return total_odds, payout, profit

    def _combo_refs(tips: List[Dict[str, Any]]) -> str:
        refs: List[str] = []
        for t in tips:
            fid = t.get("fixture_id")
            if fid in important_idx:
                refs.append(f"#{important_idx[fid]}")
        return ", ".join(refs)

    # COMBO #1 (do not repeat full match blocks; reference IMPORTANT list)
    if main1:
        o, pay, prof = _combo_totals(main1)
        vip_lines.append(f"\n🎫 <b>KOMBI #1</b> ({len(main1)} meccs)")
        if o:
            vip_lines.append(f"💰 Ha {STAKE_HUF} Ft a tét: odds≈{o:.2f} | kifizetés≈{pay} Ft | profit≈{prof} Ft")
        else:
            vip_lines.append(f"💰 Ha {STAKE_HUF} Ft a tét: kifizetés nem számolható (nincs odds minden meccshez).")
        refs = _combo_refs(main1)
        if refs:
            vip_lines.append(f"📌 Meccsek: {refs} (lásd fent)")

        vip_lines_en.append(f"\n🎫 COMBO #1 ({len(main1)} picks)")
        if o:
            vip_lines_en.append(f"💰 If stake is {STAKE_HUF} HUF: total odds≈{o:.2f} | payout≈{pay} | profit≈{prof}")

    # COMBO #2 (skip if empty)
    if main2:
        o2, pay2, prof2 = _combo_totals(main2)
        vip_lines.append(f"\n🎫 <b>KOMBI #2</b> ({len(main2)} meccs)")
        if o2:
            vip_lines.append(f"💰 Ha {STAKE_HUF} Ft a tét: odds≈{o2:.2f} | kifizetés≈{pay2} Ft | profit≈{prof2} Ft")
        else:
            vip_lines.append(f"💰 Ha {STAKE_HUF} Ft a tét: kifizetés nem számolható (nincs odds minden meccshez).")
        refs2 = _combo_refs(main2)
        if refs2:
            vip_lines.append(f"📌 Meccsek: {refs2} (lásd fent)")

        vip_lines_en.append(f"\n🎫 COMBO #2 ({len(main2)} picks)")
        if o2:
            vip_lines_en.append(f"💰 If stake is {STAKE_HUF} HUF: total odds≈{o2:.2f} | payout≈{pay2} | profit≈{prof2}")

    # BOLD / RISKY section (user can play it optionally)
    risky = (vip_bonus or []) + (vip_unsafe_extra or [])
    if risky:
        vip_lines.append(f"\n😈 <b>MERÉSZ RÉSZ</b> (opcionális) – {len(risky)} tipp")
        vip_lines.append("🙂 Játsszd, ha akarod (nagyobb kockázat / nagyobb odds).")

        vip_lines_en.append(f"\n😈 BOLD PICKS (optional) – {len(risky)}")
        vip_lines_en.append("🙂 Play only if you want higher risk / higher odds.")

        for t in risky:
            t["shelf"] = "BOLD"

        for j, t in enumerate(risky, 1):
            m = id_to_match.get(t["fixture_id"])
            label = _build_match_label(m)
            _append_tip_block(vip_lines, vip_lines_en, j, t, label)

    def _is_safe_free(t: Dict[str, Any]) -> bool:
        # If odds are available, enforce the FREE safe odds window.
        # If odds are missing, allow SAFE only when confidence is decent and risk is not high.
        risk = (t.get("risk_level") or "").lower()
        if "magas" in risk:
            return False

        odds_val = _safe_float(t.get("odds_estimate"))
        if odds_val and odds_val > 1.01:
            mn = float(os.getenv("TIPPMIX_FREE_SAFE_ODDS_MIN", str(FREE_ODDS_MIN)))
            mx = float(os.getenv("TIPPMIX_FREE_SAFE_ODDS_MAX", str(FREE_ODDS_MAX)))
            if odds_val > mx or odds_val < mn:
                return False
            return True

        conf = _safe_float(t.get("confidence")) or 0
        return conf >= 3.8

    safe_pool = [t for t in free if _is_safe_free(t)]
    risky_pool = [t for t in free if t not in safe_pool]

    free_safe = safe_pool[: max(0, FREE_SAFE_COUNT)]
    free_risky = risky_pool[: max(0, FREE_RISKY_COUNT)]

    free_lines = [
        "👑⚽️ SZELVÉNYKIRÁLY FREE – NAPI TIPPEK ⚽️👑",
        f"📅 Dátum: {today}.",
        "🙂 SAFE csak akkor, ha tényleg SAFE (nem piros).",
        f"✅ <b>BIZTOSABB</b> ({len(free_safe)} tipp)",
    ]

    free_lines_en = [
        "👑⚽️ BETSLIPKING – FREE PICKS ⚽️👑",
        f"📅 Date: {today}.",
        "🙂 SAFE only when it’s truly safe (no red/high-risk).",
        f"✅ SAFER ({len(free_safe)} picks)",
    ]

    if not free_safe:
        free_lines.append("⚠️ Ma nincs elég igazán SAFE meccs ebben az odds-ablakban.")
        free_lines.append("➡️ Nézd meg a VIP listát (PRO/Standard), vagy játssz csak a MERÉSZ részből, ha vállalod.")

        free_lines_en.append("⚠️ Not enough truly SAFE matches in the safe odds window today.")
        free_lines_en.append("➡️ Check VIP (PRO/Standard), or play BOLD only if you accept higher risk.")

    for i, t in enumerate(free_safe, 1):
        m = id_to_match.get(t["fixture_id"])
        label = _build_match_label(m)
        _append_tip_block(free_lines, free_lines_en, i, t, label)

    if free_risky:
        free_lines.append("━━━━━━━━━━━━━━━━━━━━")
        free_lines.append(f"😈 <b>MERÉSZEBB</b> (FREE {len(free_risky)} tipp)")
        free_lines.append("🙂 Opcionális – csak ha szeretsz nagyobb oddsot/kockázatot.")

        free_lines_en.append("━━━━━━━━━━━━━━━━━━━━")
        free_lines_en.append(f"😈 RISKIER ({len(free_risky)} picks)")
        free_lines_en.append("🙂 Optional – higher odds / higher risk.")

        for j, t in enumerate(free_risky, 1):
            m = id_to_match.get(t["fixture_id"])
            label = _build_match_label(m)
            _append_tip_block(free_lines, free_lines_en, j, t, label)

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
            "shelf": t.get("shelf"),
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
            "shelf": t.get("shelf"),
            "league": id_to_match[t["fixture_id"]].get("league"),
            "country": id_to_match[t["fixture_id"]].get("country"),
            "kickoff": id_to_match[t["fixture_id"]].get("kickoff"),
        }
        for t in free
    ]

    promo_hu = _promo_footer(today_iso=datetime.date.today().isoformat(), lang="hu")
    promo_en = _promo_footer(today_iso=datetime.date.today().isoformat(), lang="en")

    return {
        "telegram_public_text": "\n\n".join(free_lines) + promo_hu,
        "telegram_vip_text": "\n\n".join(vip_lines) + promo_hu,
        "telegram_public_text_en": "\n\n".join(free_lines_en) + promo_en,
        "telegram_vip_text_en": "\n\n".join(vip_lines_en) + promo_en,
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
