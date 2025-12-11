import os
import json
import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Hány meccset adjunk át maximum az OpenAI-nak (token kímélés)
MAX_MATCHES_FOR_OPENAI = 40

# Cél darabszámok
PUBLIC_MIN_TIPS = 3
VIP_MIN_TIPS = 5

# FREE / VIP odds limit (ésszerűbb tartományok)
PUBLIC_MAX_ODDS = 1.80   # FREE: stabilabb
VIP_MAX_ODDS = 2.20      # VIP: bátrabb, de nem őrült


# -------------------------------------------------------------------
# SEGÉDFÜGGVÉNYEK – FORMÁK, GÓLÁTALAGOK, TIPPEK
# -------------------------------------------------------------------

def _format_match_for_prompt(match: Dict[str, Any]) -> str:
    """
    Meccset rövid szöveggé alakítjuk – formával, gólátlaggal, fixture ID-val.
    """
    sport = match.get("sport") or match.get("sport_name") or "football"
    home = (
        match.get("home_team")
        or match.get("home_name")
        or match.get("home")
        or "Hazai csapat"
    )
    away = (
        match.get("away_team")
        or match.get("away_name")
        or match.get("away")
        or "Vendég csapat"
    )
    league = match.get("league_name") or match.get("league") or ""
    country = match.get("country_name") or match.get("country") or ""
    kickoff = (
        match.get("kickoff_local")
        or match.get("kickoff")
        or match.get("datetime")
        or match.get("date")
        or ""
    )

    fixture_id = match.get("fixture_id") or match.get("id") or ""

    home_form = match.get("home_form")
    away_form = match.get("away_form")
    haf = match.get("home_avg_goals_for")
    haa = match.get("home_avg_goals_against")
    aaf = match.get("away_avg_goals_for")
    aaa = match.get("away_avg_goals_against")

    def _fmt_goals(x: Any) -> str:
        if x is None:
            return "n.a."
        try:
            return f"{float(x):.2f}"
        except Exception:
            return str(x)

    stats_parts: List[str] = []
    if home_form or away_form:
        stats_parts.append(
            f"Forma (hazai/vendég): {home_form or 'n.a.'} / {away_form or 'n.a.'}"
        )
    if any(v is not None for v in [haf, haa, aaf, aaa]):
        stats_parts.append(
            "Gólátlagok (lőtt/kapott, hazai / vendég): "
            f"{_fmt_goals(haf)}/{_fmt_goals(haa)} vs {_fmt_goals(aaf)}/{_fmt_goals(aaa)}"
        )

    parts = [sport.capitalize(), f"{home} vs {away}"]
    if league or country:
        parts.append(f"{league} {country}".strip())
    if kickoff:
        parts.append(str(kickoff))
    if stats_parts:
        parts.append(" | ".join(stats_parts))
    if fixture_id:
        parts.append(f"[ID={fixture_id}]")

    return " | ".join(parts)


def _build_matches_prompt(matches: List[Dict[str, Any]]) -> str:
    return "\n".join(f"{idx}. {_format_match_for_prompt(m)}"
                     for idx, m in enumerate(matches, start=1))


def _odds_to_float(odds: Any) -> Optional[float]:
    if odds is None:
        return None
    if isinstance(odds, (int, float)):
        return float(odds)
    try:
        s = str(odds).strip().replace(",", ".")
        return float(s)
    except Exception:
        return None


def _form_score(form: Optional[str]) -> float:
    """
    Egyszerű formapontszám:
      W = +1
      D = 0
      L = -1
    max. 5 karakterig nézzük.
    """
    if not form:
        return 0.0
    form = form.strip().upper()
    score = 0.0
    for ch in form[:5]:
        if ch == "W":
            score += 1.0
        elif ch == "L":
            score -= 1.0
    return score


def _derive_risk_level(conf: Any, odds_float: Optional[float]) -> str:
    try:
        c = int(conf)
    except Exception:
        c = 3

    if odds_float is None:
        if c >= 4:
            return "low"
        if c <= 2:
            return "high"
        return "medium"

    o = odds_float

    if o <= 1.40:
        if c >= 4:
            return "low"
        if c <= 2:
            return "medium"
        return "medium"

    if o <= 1.80:
        if c >= 4:
            return "medium"
        if c <= 2:
            return "high"
        return "medium"

    if o <= 2.50:
        if c >= 4:
            return "medium"
        if c <= 2:
            return "high"
        return "medium"

    return "high"


def _risk_to_emoji(conf: Any, odds_float: Optional[float]) -> str:
    level = _derive_risk_level(conf, odds_float)
    if level == "low":
        return "🟢 alacsony (stabilabb)"
    if level == "high":
        return "🔴 magas (kockázatosabb)"
    return "🟠 közepes"


def _confidence_to_stars(conf: Any) -> str:
    try:
        c = int(conf)
    except Exception:
        c = 3
    c = max(1, min(5, c))
    return "⭐" * c + f" ({c}/5)"


def _is_double_chance_tip(tip: str) -> bool:
    t = (tip or "").lower()
    patterns = [
        "1x",
        "x2",
        "12",
        "hazai vagy döntetlen",
        "vendég vagy döntetlen",
        "döntetlen vagy hazai",
        "döntetlen vagy vendég",
    ]
    return any(p in t for p in patterns)


def _make_more_aggressive_tip(tip: str) -> str:
    t = (tip or "").lower()
    if ("hazai" in t and "döntetlen" in t) or "1x" in t:
        return "Hazai győzelem"
    if ("vendég" in t and "döntetlen" in t) or "x2" in t:
        return "Vendég győzelem"
    if "12" in t:
        return "Hazai győzelem"
    return tip


def _clean_reason(reason: str) -> str:
    r = reason or ""
    for pat in ["1x", "1X"]:
        r = r.replace(pat, "hazai oldal")
    for pat in ["x2", "X2"]:
        r = r.replace(pat, "vendég oldal")
    r = r.replace("biztonságosabb", "óvatosabb")
    return r


def _truncate_reason(reason: str, max_len: int = 220) -> str:
    reason = reason or ""
    if len(reason) > max_len:
        reason = reason[: max_len - 3].rstrip() + "..."
    return _clean_reason(reason)


def _choose_fallback_market(match: Dict[str, Any], for_vip: bool) -> tuple[str, float, str]:
    """
    Egyszerű, stat-alapú fallback:
      - ha gólgazdag a párosítás → Over 2.5 gól
      - különben az erősebb oldal: hazai vagy vendég győzelem
    """
    home_form = match.get("home_form")
    away_form = match.get("away_form")
    haf = match.get("home_avg_goals_for")
    haa = match.get("home_avg_goals_against")
    aaf = match.get("away_avg_goals_for")
    aaa = match.get("away_avg_goals_against")

    home_score = _form_score(home_form)
    away_score = _form_score(away_form)

    def _to_float(x: Any) -> Optional[float]:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        try:
            return float(str(x).replace(",", "."))
        except Exception:
            return None

    haf_f = _to_float(haf)
    haa_f = _to_float(haa)
    aaf_f = _to_float(aaf)
    aaa_f = _to_float(aaa)

    if haf_f is not None and haa_f is not None:
        home_score += (haf_f - haa_f)
    if aaf_f is not None and aaa_f is not None:
        away_score += (aaf_f - aaa_f)

    goals_sum = None
    if haf_f is not None and aaf_f is not None:
        goals_sum = haf_f + aaf_f

    if goals_sum is not None and goals_sum >= 3.0:
        odds = 1.85 if for_vip else 1.70
        reason = "A két csapat gólátlaga alapján a gólpiac (Over 2.5) ígéretes választás lehet."
        return "Over 2.5 gól", odds, reason

    if home_score >= away_score:
        odds = 1.70 if for_vip else 1.45
        reason = "A hazai csapat formája és gólmutatója alapján a hazai oldal felé billen az esély."
        return "Hazai győzelem", odds, reason
    else:
        odds = 1.90 if for_vip else 1.60
        reason = "A vendég csapat formája és gólmutatója alapján a vendég oldal felé billen az esély."
        return "Vendég győzelem", odds, reason


def _build_simple_bet_from_match(match: Dict[str, Any]) -> Dict[str, Any]:
    desc = _format_match_for_prompt(match)
    fixture_id = match.get("fixture_id") or match.get("id")
    tip, odds, reason = _choose_fallback_market(match, for_vip=False)
    return {
        "match": desc,
        "fixture_id": fixture_id,
        "tip": tip,
        "odds": odds,
        "confidence": 3,
        "reason": reason,
    }


def _build_vip_fallback_bet(match: Dict[str, Any]) -> Dict[str, Any]:
    desc = _format_match_for_prompt(match)
    fixture_id = match.get("fixture_id") or match.get("id")
    tip, odds, reason = _choose_fallback_market(match, for_vip=True)
    return {
        "match": desc,
        "fixture_id": fixture_id,
        "tip": tip,
        "odds": odds,
        "confidence": 3,
        "reason": reason,
    }


def _filter_by_max_odds(bets: List[Dict[str, Any]], max_odds: float) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for bet in bets:
        odds_float = _odds_to_float(bet.get("odds"))
        if odds_float is None or odds_float <= max_odds:
            filtered.append(bet)
    return filtered


def _select_featured_vip_bets(vip_bets: List[Dict[str, Any]], max_count: int = 3) -> List[Dict[str, Any]]:
    """
    3 'kiemelt' VIP tipp:
      - alacsonyabb kockázat
      - alacsonyabb odds
      - magasabb confidence
    """
    scored: List[tuple] = []

    for bet in vip_bets:
        odds_float = _odds_to_float(bet.get("odds"))
        conf_val = bet.get("confidence", 3)

        if odds_float is None:
            odds_f = 2.0
        else:
            odds_f = float(odds_float)

        risk_level = _derive_risk_level(conf_val, odds_float)
        if risk_level == "low":
            risk_weight = 0
        elif risk_level == "medium":
            risk_weight = 1
        else:
            risk_weight = 2

        sort_key = (risk_weight, odds_f, -int(conf_val))
        scored.append((sort_key, bet))

    scored.sort(key=lambda x: x[0])
    return [bet for _, bet in scored[:max_count]]


# -------------------------------------------------------------------
# TELEGRAM SZÖVEGÉPÍTŐK
# -------------------------------------------------------------------

def _build_public_text(data: Dict[str, Any]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    public_bets = data.get("public_bets") or []

    header = (
        f"👑 SZELVÉNYKIRÁLY – FREE TIPPEK MA ESTÉRE 👑\n"
        f"({today} – max 3 stabilabb tipp)\n\n"
        "Az alábbi meccsek a statisztika, forma és keretek alapján ígéretesek "
        "egy stabilabb, ésszerű kombira:\n"
    )

    if not public_bets:
        body = (
            "Ma kevés igazán stabil FREE lehetőséget találtunk, "
            "ezért inkább visszafogottan játssz. 🙂"
        )
    else:
        lines: List[str] = []
        for i, bet in enumerate(public_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = bet.get("tip") or "Hazai győzelem"
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = bet.get("reason") or "Statisztika és forma alapján értelmes választás."
            reason = _clean_reason(reason)
            conf_val = bet.get("confidence", 3)
            risk = _risk_to_emoji(conf_val, odds_float)
            conf = _confidence_to_stars(conf_val)

            line_parts = [
                f"{i}. Meccs: {match}",
                f"Tipp: {tip}",
            ]
            if odds:
                line_parts.append(f"Odd: {odds}")
            line_parts.append(f"Kockázat: {risk}")
            line_parts.append(f"Bizalom: {conf}")
            line_parts.append(f"Miért? {reason}")

            lines.append("\n".join(line_parts))

        body = "\n\n".join(lines)

    bankroll_hint = (
        "\n\n💰 Bankroll tipp (FREE):\n"
        "Egy szelvényre legfeljebb a teljes kereted 1–2%-át tedd fel.\n"
        "Ha pl. 100.000 Ft a bankrollod, akkor 1–2.000 Ft/szelvény az ésszerű tartomány.\n"
        "Ne üldözd a veszteségeket, gondolkodj hosszú távon. 🍀"
    )

    return header + body + bankroll_hint


def _build_vip_text(data: Dict[str, Any]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    vip_bets = data.get("vip_bets") or []
    edu_tip = data.get("edu_tip") or (
        "Mindig bankrollból fogadj, ne abból a pénzből, amire a mindennapi kiadásokhoz szükséged van."
    )

    header = (
        f"🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI MA ESTÉRE 🔥\n"
        f"({today} – 5–7 gondosan válogatott tipp, nagyobb összodds)\n\n"
        "Ezek a meccsek kombinálva erősebb, de még ésszerűen vállalható kockázatú VIP szelvényt adnak:\n"
    )

    if not vip_bets:
        body = (
            "Ma kevés az igazán jó VIP kombinációs lehetőség – ilyenkor jobb a kisebb akció, "
            "mint az erőltetett nagy odds. 🤝"
        )
        total_odds_line = ""
        featured_block = ""
    else:
        featured_bets = _select_featured_vip_bets(vip_bets, max_count=3)
        featured_ids = {id(b) for b in featured_bets}

        lines: List[str] = []
        approx_total_odds = 1.0
        featured_total_odds = 1.0
        featured_has_odds = False

        for i, bet in enumerate(vip_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = bet.get("tip") or "Hazai győzelem / gólpiac"
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = bet.get("reason") or "Forma, statisztika és keret alapján jó esély mutatkozik."
            reason = _clean_reason(reason)
            conf_val = bet.get("confidence", 3)
            risk = _risk_to_emoji(conf_val, odds_float)
            conf = _confidence_to_stars(conf_val)

            if isinstance(odds, (int, float)):
                approx_total_odds *= float(odds)
            else:
                try:
                    approx_total_odds *= float(str(odds).replace(",", "."))
                except Exception:
                    pass

            if id(bet) in featured_ids and odds_float is not None:
                featured_total_odds *= float(odds_float)
                featured_has_odds = True

            if id(bet) in featured_ids:
                title_line = f"{i}. ⭐ KIEMELT meccs: {match}"
            else:
                title_line = f"{i}. Meccs: {match}"

            line_parts = [
                title_line,
                f"Tipp: {tip}",
            ]
            if odds:
                line_parts.append(f"Odd: {odds}")
            line_parts.append(f"Kockázat: {risk}")
            line_parts.append(f"Bizalom: {conf}")
            line_parts.append(f"Miért? {reason}")

            lines.append("\n".join(line_parts))

        body = "\n\n".join(lines)

        if featured_has_odds and featured_total_odds > 1.01:
            example_win = featured_total_odds * 2000
            featured_block = (
                f"\n\n🎯 KIEMELT 3-AS KOMBI (óvatosabb)\n"
                f"A fenti listából 3 kiemelt meccs, statisztika és kockázat alapján válogatva.\n"
                f"Összodds: kb. {featured_total_odds:.2f}\n"
                f"Példa tét: 2.000 Ft → várható nyeremény: kb. {example_win:,.0f} Ft"
            )
        else:
            featured_block = ""

        if approx_total_odds > 1.01:
            total_odds_line = (
                f"\n\n📊 TELJES VIP KOMBI ÖSSZODDS: kb. {approx_total_odds:.2f}\n"
                "Példa tét: 5.000 Ft → várható nyeremény: kb. "
                f"{approx_total_odds*5000:,.0f} Ft (bruttó, tájékoztató jelleggel)."
            )
        else:
            total_odds_line = ""

    bankroll_hint = (
        "\n\n💰 Bankroll tipp (VIP):\n"
        "VIP szelvényre maximum a bankrollod 1–3%-át érdemes tenni.\n"
        "Ha pl. 200.000 Ft a kereted, akkor 2–6.000 Ft/szelvény még ésszerű.\n"
        "Kerüld a tétemelést csak azért, mert az előző szelvény nyert vagy vesztett."
    )

    edu_block = f"\n\n🎓 Napi mini tanács:\n{edu_tip}"

    return header + body + featured_block + total_odds_line + bankroll_hint + edu_block


# -------------------------------------------------------------------
# BET-LISTA TISZTÍTÁSA / MINIMUM DARABSZÁM
# -------------------------------------------------------------------

def _ensure_min_bets(data: Dict[str, Any], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    public = data.get("public_bets") or []
    vip = data.get("vip_bets") or []

    for bet in public + vip:
        if "reason" in bet:
            bet["reason"] = _truncate_reason(str(bet.get("reason", "")))

    # FREE: dupla esély agresszívabbra írva
    for bet in public:
        tip_old = str(bet.get("tip", ""))
        if _is_double_chance_tip(tip_old):
            bet["tip"] = _make_more_aggressive_tip(tip_old)

    public = _filter_by_max_odds(public, PUBLIC_MAX_ODDS)

    already_used_public = {b.get("match") for b in public}
    for m in matches:
        if len(public) >= PUBLIC_MIN_TIPS:
            break
        desc = _format_match_for_prompt(m)
        if desc in already_used_public:
            continue
        bet = _build_simple_bet_from_match(m)
        public.append(bet)
        already_used_public.add(desc)

    # VIP: dupla esély TILOS
    vip_filtered: List[Dict[str, Any]] = []
    for bet in vip:
        tip = str(bet.get("tip", ""))
        if _is_double_chance_tip(tip):
            continue
        vip_filtered.append(bet)
    vip = vip_filtered

    vip = _filter_by_max_odds(vip, VIP_MAX_ODDS)

    already_used_vip = {b.get("match") for b in vip}
    for m in matches:
        if len(vip) >= VIP_MIN_TIPS:
            break
        desc = _format_match_for_prompt(m)
        if desc in already_used_vip:
            continue
        bet = _build_vip_fallback_bet(m)
        vip.append(bet)
        already_used_vip.add(desc)

    data["public_bets"] = public
    data["vip_bets"] = vip
    return data


# -------------------------------------------------------------------
# OPENAI HÍVÁS
# -------------------------------------------------------------------

def _call_openai_for_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    trimmed = matches[:MAX_MATCHES_FOR_OPENAI]
    print(f"OpenAI felé küldött meccsek száma: {len(trimmed)}")

    matches_text = _build_matches_prompt(trimmed)
    today = datetime.date.today().strftime("%Y.%m.%d.")

    system_msg = (
        "Te egy felelős sportfogadás-elemző asszisztens vagy. "
        "Nem ígérsz biztos nyereményt, hanem statisztika, forma, sérülések, "
        "pályaelőny alapján próbálsz ÉSSZERŰ tippeket adni. "
        "Mindig hangsúlyozd, hogy a sportfogadás kockázatos."
    )

    user_msg = f"""
Dátum: {today}

Az alábbi meccsek közül kell FREE és VIP tippeket választanod.
A meccsek listája (röviden, forma + gólátlagokkal együtt):

{matches_text}

Cél:
- FREE csatorna: inkább stabil favoritokra építő, alacsonyabb oddsú tippek.
- VIP csatorna: bátrabb, de még mindig ÉSSZERŰ favoritokra és gólpiacokra építő tippek.

Fontos:
- NE válassz nagy underdogokat vagy puszta meglepetést.
- Ne adj tiszta döntetlent, csak ha nagyon indokolt – inkább 1 vagy 2, vagy gólpiac.
- Használd a megadott formát (WDWLW...) és gólátlagokat a döntésben.
- Törekedj VEGYES piacokra: legyenek hazai/vendég győzelmek és gólpiacok is,
  ne legyen minden tipp ugyanarra a típusra (pl. csak hazai győzelem).

Konkrét szabályok:

1) FREE (public_bets):
   - Válassz LEGALÁBB 1 és legfeljebb 3 mérkőzést.
   - Itt csak viszonylag stabil, alacsonyabb oddsú tippet adj.
   - Lehetőleg 1.25–1.80 közötti decimális odds tartományban maradj.

2) VIP (vip_bets):
   - Válassz LEGALÁBB 5 és legfeljebb 7 mérkőzést.
   - Itt lehet kicsit bátrabb (pl. 1.40–2.20 odds tartományban), de ne szélsőséges underdogokat játssz.
   - Törekedj arra, hogy ne legyen minden tipp ugyanaz (pl. ne legyen mind hazai győzelem),
     használj vegyesen 1, 2 és gólpiac tippeket (Over 2.5, mindkét csapat szerez gólt, stb.).

3) Minden kiválasztott meccshez add meg:
   - match: rövid leírás pl. "Manchester United vs West Ham (Premier League, 20:00) [ID=12345]"
   - fixture_id: a fenti sorban szereplő [ID=12345] értéke számként (ha van ilyen)
   - tip: EGYÉRTELMŰ, KONKRÉT fogadási ötlet (pl. "Hazai győzelem", "Vendég győzelem", "Over 2.5 gól")
   - odds: reális decimális odd (pl. 1.65, 1.90, 2.10), akár becsült érték
   - risk: low / medium / high (kockázat szintje, odds + logika alapján)
   - confidence: 1–5 közötti szám, hogy mennyire bízol a tippedben
   - reason: maximum 1–2 mondatos indoklás (max ~220 karakter),
             forma, statisztika, hazai pálya, sérülések, motiváció, stb. alapján.

Korlátozások:
- Ugyanaz a meccs a public_bets és vip_bets listában legfeljebb EGYSZER szerepelhet.
- Ne ismételd szó szerint ugyanazt az indoklást minden meccsnél, legyen természetes, de tömör.

4) Adj egy nagyon rövid, 1 mondatos oktató tippet is:
   - edu_tip: pl. "Ne emeld a tétet csak azért, mert az előző szelvény vesztett."

FORMÁTUM:
Kizárólag ÉRVÉNYES JSON-t adj vissza, minden egyéb szöveg nélkül!
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=1300,
        temperature=0.3,
    )

    content = response.choices[0].message.content
    print("OpenAI raw válasz (első 500 karakter):")
    print((content or "")[:500])

    data = json.loads(content)
    data = _ensure_min_bets(data, trimmed)
    return data


# -------------------------------------------------------------------
# FŐ FÜGGVÉNY – MAIN.PY EZT HÍVJA
# -------------------------------------------------------------------

def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Visszaadja:
      - telegram_public_text
      - telegram_vip_text
      - public_bets
      - vip_bets
    """
    try:
        data = _call_openai_for_tips(matches)
        public_text = _build_public_text(data)
        vip_text = _build_vip_text(data)
        return {
            "telegram_public_text": public_text,
            "telegram_vip_text": vip_text,
            "public_bets": data.get("public_bets", []),
            "vip_bets": data.get("vip_bets", []),
        }
    except Exception as e:
        print("HIBA az OpenAI hívás során, fallback logikát használunk.")
        print("Részletek:", repr(e))

        today = datetime.date.today().strftime("%Y.%m.%d.")
        trimmed = matches[:10]

        lines_public: List[str] = []
        for i, m in enumerate(trimmed[:3], start=1):
            desc = _format_match_for_prompt(m)
            lines_public.append(
                f"{i}. Meccs: {desc}\n"
                f"Tipp: Hazai győzelem (óvatos oddszal)."
            )

        public_body = (
            "\n\n".join(lines_public)
            if lines_public
            else "Ma kevés publikus lehetőség látszik."
        )

        public_text = (
            f"👑 SZELVÉNYKIRÁLY – FREE TIPPEK (fallback mód) 👑\n"
            f"({today})\n\n"
            "Technikai hiba miatt most egyszerűsített tippek érkeznek, "
            "részletes AI elemzés nélkül.\n\n"
            + public_body
            + "\n\n💰 Bankroll tipp: max 1–2% keret tétben, és mindig felelősen játssz."
        )

        lines_vip: List[str] = []
        for i, m in enumerate(trimmed[:7], start=1):
            desc = _format_match_for_prompt(m)
            lines_vip.append(
                f"{i}. Meccs: {desc}\n"
                f"Tipp: Hazai győzelem vagy gólpiac (kicsit bátrabb oddszal)."
            )

        vip_body = (
            "\n\n".join(lines_vip)
            if lines_vip
            else "Ma kevés VIP lehetőség látszik."
        )

        vip_text = (
            f"🔥 SZELVÉNYKIRÁLY VIP – FALLBACK SZELVÉNY 🔥\n"
            f"({today})\n\n"
            "Az AI elemzés most technikai okokból nem elérhető, ezért egyszerűbb, óvatos VIP ötleteket kapsz.\n\n"
            + vip_body
            + "\n\n💰 Bankroll tipp: VIP-ben se lépd túl a bankrollod 1–3%-át szelvényenként."
            + "\n\n🎓 Mini tanács: Technikai hiba esetén se erőltesd a játékot – a sportfogadás maradjon szórakozás."
        )

        fallback_public_bets = [
            {"match": _format_match_for_prompt(m), "tip": "Hazai győzelem"}
            for m in trimmed[:3]
        ]
        fallback_vip_bets = [
            {"match": _format_match_for_prompt(m), "tip": "Hazai győzelem"}
            for m in trimmed[:7]
        ]

        return {
            "telegram_public_text": public_text,
            "telegram_vip_text": vip_text,
            "public_bets": fallback_public_bets,
            "vip_bets": fallback_vip_bets,
        }
