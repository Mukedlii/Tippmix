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
VIP_MIN_TIPS = 7  # 7 VIP tipp, ebből választunk kiemelt 3-at


# -----------------------------
# Segédfüggvények – formázás
# -----------------------------
def _format_match_for_prompt(match: Dict[str, Any]) -> str:
    """
    Meccs objektumot rövid, szöveges sorra alakítjuk.
    Ha van fixture_id, azt [ID=...] formában tesszük a végére.
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

    parts = [sport.capitalize(), f"{home} vs {away}"]
    if league or country:
        parts.append(f"{league} {country}".strip())
    if kickoff:
        parts.append(str(kickoff))
    if fixture_id:
        parts.append(f"[ID={fixture_id}]")

    return " | ".join(parts)


def _build_matches_prompt(matches: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, m in enumerate(matches, start=1):
        lines.append(f"{idx}. {_format_match_for_prompt(m)}")
    return "\n".join(lines)


def _odds_to_float(odds: Any) -> Optional[float]:
    """
    Odds mezőt próbáljuk float-tá alakítani.
    Elfogadjuk: 1.75, "1.75", "1,75" formákat.
    """
    if odds is None:
        return None
    if isinstance(odds, (int, float)):
        return float(odds)
    try:
        s = str(odds).strip().replace(",", ".")
        return float(s)
    except Exception:
        return None


# -----------------------------
# Kockázat / bizalom
# -----------------------------
def _derive_risk_level(conf: Any, odds_float: Optional[float]) -> str:
    """
    Bizalom (1–5) + odds alapján állapítjuk meg a kockázat szintjét:
      - 'low'    -> zöld
      - 'medium' -> narancs
      - 'high'   -> piros

    Logika – hogy a "5 csillag + alacsony odds" tényleg zöld legyen:
      - 1.00–1.55: ha conf >= 4 → low, ha conf <= 2 → medium, különben medium
      - 1.56–1.85: ha conf >= 4 → low, ha conf <= 2 → high, különben medium
      - 1.86–2.30: ha conf >= 4 → medium, ha conf <= 2 → high, különben medium
      - 2.30 felett: többnyire high (kivéve ha conf = 5 → medium)
    """
    try:
        c = int(conf)
    except Exception:
        c = 3

    if odds_float is None:
        if c >= 4:
            return "medium"
        if c <= 2:
            return "high"
        return "medium"

    o = odds_float

    if o <= 1.55:
        if c >= 4:
            return "low"
        if c <= 2:
            return "medium"
        return "medium"

    if o <= 1.85:
        if c >= 4:
            return "low"
        if c <= 2:
            return "high"
        return "medium"

    if o <= 2.30:
        if c <= 2:
            return "high"
        return "medium"

    # 2.30 fölött
    if c == 5:
        return "medium"
    return "high"


def _risk_to_emoji(conf: Any, odds_float: Optional[float]) -> str:
    """
    A kockázat színét a confidence + odds alapján döntjük el.
      - low    -> 🟢 alacsony (stabilabb)
      - medium -> 🟠 közepes
      - high   -> 🔴 magas (kockázatosabb)
    """
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


# -----------------------------
# Tipp tisztítás – dupla esély, BTTS
# -----------------------------
def _is_double_chance_tip(tip: str) -> bool:
    """
    Eldönti, hogy a tipp dupla esély-e (1X, X2, 12, hazai vagy döntetlen, stb.).
    """
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
    """
    Dupla esélyből csinál 'egyszínű' tippet:
      - 'hazai vagy döntetlen' / '1X' -> 'Hazai győzelem'
      - 'vendég vagy döntetlen' / 'X2' -> 'Vendég győzelem'
      - '12' -> 'Hazai győzelem'
    """
    t = (tip or "").lower()
    if "hazai" in t and "döntetlen" in t or "1x" in t:
        return "Hazai győzelem"
    if "vendég" in t and "döntetlen" in t or "x2" in t:
        return "Vendég győzelem"
    if "12" in t:
        return "Hazai győzelem"
    return tip


def _replace_btts_tip(tip: str) -> str:
    """
    BTTS ('mindkét csapat szerez gólt', 'btts') helyett egyszerűbb piacot használunk:
      - alapértelmezés: 'Over 2.5 gól'
    Ha a tipp nem BTTS, változatlanul hagyjuk.
    """
    t = (tip or "").lower()
    if "mindkét csapat szerez gólt" in t or "btts" in t:
        return "Over 2.5 gól"
    return tip


def _clean_reason(reason: str) -> str:
    """
    Tisztítja a magyarázatot:
      - kiszedi az 1X / X2 jelölést
      - a 'biztonságosabb' szót 'óvatosabb'-ra cseréli
    """
    r = reason or ""
    for pat in ["1x", "1X"]:
        r = r.replace(pat, "hazai oldal")
    for pat in ["x2", "X2"]:
        r = r.replace(pat, "vendég oldal")
    r = r.replace("biztonságosabb", "óvatosabb")
    return r


def _truncate_reason(reason: str, max_len: int = 220) -> str:
    """
    Ne legyenek végtelen hosszú magyarázatok – max ~2 mondat + tisztítás.
    """
    reason = reason or ""
    if len(reason) > max_len:
        reason = reason[: max_len - 3].rstrip() + "..."
    return _clean_reason(reason)


# -----------------------------
# Szöveg – FREE
# -----------------------------
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
            "Ma kevés igazán stabil FREE lehetőséget találtunk, ezért inkább visszafogottan játssz. 🙂"
        )
    else:
        lines: List[str] = []
        for i, bet in enumerate(public_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = bet.get("tip") or "Hazai győzelem"
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = _truncate_reason(str(bet.get("reason", "")))
            conf_val = bet.get("confidence", 3)
            risk = _risk_to_emoji(conf_val, odds_float)
            conf = _confidence_to_stars(conf_val)

            line_parts = [
                f"{i}. Meccs: {match}",
                f"   Tipp: {tip}",
            ]
            if odds:
                line_parts.append(f"   Odd: {odds}")
            line_parts.append(f"   Kockázat: {risk}")
            line_parts.append(f"   Bizalom: {conf}")
            line_parts.append(f"   Miért? {reason}")

            lines.append("\n".join(line_parts))

        body = "\n\n".join(lines)

    bankroll_hint = (
        "\n\n💰 Bankroll tipp (FREE):\n"
        "Egy szelvényre legfeljebb a teljes kereted 1–2%-át tedd fel.\n"
        "Ha pl. 100.000 Ft a bankrollod, akkor 1–2.000 Ft/szelvény az ésszerű tartomány.\n"
        "Ne üldözd a veszteségeket, gondolkodj hosszú távon. 🍀"
    )

    return header + body + bankroll_hint


# -----------------------------
# VIP – kiemelt meccsek kiválasztása
# -----------------------------
def _select_featured_vip_bets(vip_bets: List[Dict[str, Any]], max_featured: int = 3) -> List[Dict[str, Any]]:
    """
    Kiválasztja a 3 "kiemelt" VIP tippet:
      - először azok, ahol magasabb a confidence,
      - azon belül alacsonyabb odds (stabilabb),
      - legfeljebb max_featured darab.
    """
    scored: List[tuple] = []
    for bet in vip_bets:
        conf = bet.get("confidence", 3)
        odds_f = _odds_to_float(bet.get("odds"))
        # nagyobb conf jobb, kisebb odds stabilabb
        # sort key: (-conf, odds_f or nagy szám)
        scored.append(
            (
                -int(conf) if isinstance(conf, (int, float, str)) else -3,
                odds_f if odds_f is not None else 99.9,
                bet,
            )
        )

    scored_sorted = sorted(scored, key=lambda x: (x[0], x[1]))
    result: List[Dict[str, Any]] = []
    for _, _, bet in scored_sorted[:max_featured]:
        result.append(bet)
    return result


# -----------------------------
# Szöveg – VIP
# -----------------------------
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
        lines: List[str] = []
        approx_total_odds = 1.0

        for i, bet in enumerate(vip_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = bet.get("tip") or "Hazai győzelem"
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = _truncate_reason(str(bet.get("reason", "")))
            conf_val = bet.get("confidence", 3)
            risk = _risk_to_emoji(conf_val, odds_float)
            conf = _confidence_to_stars(conf_val)

            if odds_float is not None:
                approx_total_odds *= odds_float

            line_parts = [
                f"{i}. Meccs: {match}",
                f"   Tipp: {tip}",
            ]
            if odds:
                line_parts.append(f"   Odd: {odds}")
            line_parts.append(f"   Kockázat: {risk}")
            line_parts.append(f"   Bizalom: {conf}")
            line_parts.append(f"   Miért? {reason}")

            lines.append("\n".join(line_parts))

        body = "\n\n".join(lines)

        if approx_total_odds > 1.01:
            total_odds_line = (
                f"\n\n📊 VIP összodds (hozzávetőleges): kb. {approx_total_odds:.2f}\n"
                "Példa tét: 2.000 Ft → várható nyeremény: kb. "
                f"{approx_total_odds*2000:,.0f} Ft (bruttó, tájékoztató jelleggel)."
            )
        else:
            total_odds_line = ""

        # --- 3 kiemelt VIP meccs blokk ---
        featured = _select_featured_vip_bets(vip_bets, max_featured=3)
        if featured:
            featured_odds_product = 1.0
            featured_lines: List[str] = []
            for j, bet in enumerate(featured, start=1):
                match = bet.get("match") or "Ismeretlen meccs"
                tip = bet.get("tip") or "Hazai győzelem"
                odds = bet.get("odds")
                odds_f = _odds_to_float(odds)
                conf_val = bet.get("confidence", 3)
                conf = _confidence_to_stars(conf_val)

                if odds_f is not None:
                    featured_odds_product *= odds_f

                featured_lines.append(
                    f"{j}. {match}\n"
                    f"   Tipp: {tip} | Odd: {odds} | Bizalom: {conf}"
                )

            if featured_odds_product > 1.01:
                featured_block = (
                    "\n\n✨ 3 KIEMELT VIP TIPP – FÓKUSZ SZELEKCIÓ ✨\n"
                    "Ezek a meccsek a teljes VIP listából a legstabilabb kombinációnak számítanak "
                    "(magasabb bizalom + vállalható odds):\n\n"
                    + "\n\n".join(featured_lines)
                    + "\n\n"
                    f"🎯 Kiemelt trió összodds (hozzávetőleges): kb. {featured_odds_product:.2f}\n"
                    f"💵 Példa tét: 2.000 Ft → várható nyeremény: kb. {featured_odds_product*2000:,.0f} Ft."
                )
            else:
                featured_block = (
                    "\n\n✨ 3 KIEMELT VIP TIPP ✨\n"
                    "Ezek a meccsek a teljes VIP listából a legstabilabbak a bizalom és az odds alapján:\n\n"
                    + "\n\n".join(featured_lines)
                )
        else:
            featured_block = ""

    bankroll_hint = (
        "\n\n💰 Bankroll tipp (VIP):\n"
        "VIP szelvényre maximum a bankrollod 1–3%-át érdemes tenni.\n"
        "Ha pl. 200.000 Ft a kereted, akkor 2–6.000 Ft/szelvény még ésszerű.\n"
        "Kerüld a tétemelést csak azért, mert az előző szelvény nyert vagy vesztett."
    )

    edu_block = f"\n\n🎓 Napi mini tanács:\n{edu_tip}"

    return header + body + total_odds_line + featured_block + bankroll_hint + edu_block


# -----------------------------
# Fallback tippek – ha OpenAI elszáll
# -----------------------------
def _build_simple_bet_from_match(match: Dict[str, Any]) -> Dict[str, Any]:
    """
    FREE fallback: ha az AI nem ad elég tippet, mi gyártunk egy stabilabb sort.
    """
    desc = _format_match_for_prompt(match)
    return {
        "match": desc,
        "tip": "Hazai győzelem",
        "odds": 1.40,
        "confidence": 3,
        "reason": "Hazai pálya és forma alapján vállalható stabilabb tipp.",
    }


def _build_vip_fallback_bet(match: Dict[str, Any]) -> Dict[str, Any]:
    """
    VIP fallback tipp, dupla esély NINCS.
    Egyszerű, de egyértelmű piac: hazai győzelem.
    """
    desc = _format_match_for_prompt(match)
    return {
        "match": desc,
        "tip": "Hazai győzelem",
        "odds": 1.80,
        "confidence": 3,
        "reason": "Hazai pálya előnye és erősebb keret miatt vállalható VIP tipp.",
    }


# -----------------------------
# AI output tisztítása, minimum darabszám
# -----------------------------
def _ensure_min_bets(data: Dict[str, Any], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Gondoskodik róla, hogy mindig legyen legalább:
      - 3 FREE tipp
      - 7 VIP tipp (ha van elég meccs)

    Szabályok:
      - MINDEN dupla esélyt átváltunk tiszta 1 / X / 2-re.
      - BTTS tippet (mindkét csapat szerez gólt) kicseréljük Over 2.5 gólra.
    """
    public = data.get("public_bets") or []
    vip = data.get("vip_bets") or []

    # Reason-ek rövidítése + tisztítása, tippek tisztítása (dupla esély, BTTS)
    for bet in public + vip:
        if "reason" in bet:
            bet["reason"] = _truncate_reason(str(bet.get("reason", "")))
        if "tip" in bet:
            tip_old = str(bet.get("tip", ""))
            # először BTTS csere:
            tip_new = _replace_btts_tip(tip_old)
            # majd dupla esély csere:
            if _is_double_chance_tip(tip_new):
                tip_new = _make_more_aggressive_tip(tip_new)
            bet["tip"] = tip_new

    # PUBLIC – töltsük fel 3-ig, ha kevesebb van
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

    # VIP – töltsük fel 7-ig fallback VIP tippekkel
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


# -----------------------------
# OpenAI hívás – prompt
# -----------------------------
def _call_openai_for_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Meghívja az OpenAI-t, és JSON-t vár vissza a tippekről.
    Ha bármi gond van, exceptiont dob – ezt a generate_tips kezeli.
    """
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
A meccsek listája (röviden):

{matches_text}

Nagyon fontos LIGAVÁLASZTÁSI SZABÁLYOK:

- Előnyben részesítsd a nagyobb, ismertebb ligákat:
  - Top európai ligák (Premier League, La Liga, Serie A, Bundesliga, Ligue 1 stb.)
  - Nemzeti 1. osztályok
  - Válogatott tornák (EB, VB selejtező, Copa America stb.)
- Exotikus / alsóbb osztályú ligákból (pl. nagyon kicsi, gyengébb bajnokságok) csak akkor válassz,
  ha valóban nagyon erős value látszik, és nincs jobb alternatíva.

PIACVÁLASZTÁSI SZABÁLYOK:

- Kerüld a DUPLA ESÉLY típusú piacokat:
  - NEM használhatsz: '1X', 'X2', '12', 'hazai vagy döntetlen', 'vendég vagy döntetlen' stb.
  - A tippek legyenek egyértelműek: 'Hazai győzelem', 'Vendég győzelem', 'Döntetlen'.
- Kerüld a BTTS piacot:
  - NEM használhatsz: 'mindkét csapat szerez gólt', 'BTTS'.
- Használhatsz egyszerű gólpiacot:
  - pl. 'Over 2.5 gól', 'Under 2.5 gól', ha a statisztika ezt indokolja.

Feladatod:

1) FREE (public_bets):
   - Válaszd ki a legjobb LEGALÁBB 1 és legfeljebb 3 mérkőzést.
   - Itt inkább óvatosabb, stabilabb tippeket adj.

2) VIP (vip_bets):
   - Válaszd ki a legjobb LEGALÁBB 5 és legfeljebb 7 mérkőzést.
   - Itt lehet bátrabb az odds, de továbbra is ésszerű keretek között.
   - A VIP meccsek lehetnek részben átfedésben a FREE-vel, de nem kötelező.

3) Minden kiválasztott meccshez add meg:
   - match: rövid leírás pl. "Manchester United vs West Ham (Premier League, 20:00) [ID=12345]"
   - fixture_id: a fenti sorban szereplő [ID=12345] értéke számként (ha van ilyen)
   - tip: EGYÉRTELMŰ, KONKRÉT fogadási ötlet:
       pl. "Hazai győzelem", "Vendég győzelem", "Döntetlen", "Over 2.5 gól"
       (NINCS dupla esély, NINCS BTTS!)
   - odds: reális decimális odd (pl. 1.75, 2.10), akár becsült érték
   - risk: low / medium / high (kockázat szintje)
   - confidence: 1–5 közötti szám, hogy mennyire bízol a tippedben
   - reason: maximum 1–2 mondatos indoklás (max ~220 karakter),
             forma, statisztika, hazai pálya, sérülések, motiváció, stb. alapján.

Fontos korlátozások:

- Ugyanaz a meccs a public_bets és vip_bets listában legfeljebb EGYSZER szerepelhet (de szerepelhet mindkettőben).
- Ne ismételd szó szerint ugyanazt az indoklást minden meccsnél, legyen természetes, de tömör.
- Ne adj irreálisan alacsony (pl. 1.01) vagy irreálisan magas (pl. 20.0) oddsokat.

4) Adj egy nagyon rövid, 1 mondatos oktató tippet is:
   - edu_tip: pl. "Ne emeld a tétet csak azért, mert az előző szelvény vesztett."

FORMÁTUM:

Kizárólag ÉRVÉNYES JSON-t adj vissza, minden egyéb szöveg nélkül!

Példa struktúra:

{{
  "public_bets": [
    {{
      "match": "...",
      "fixture_id": 12345,
      "tip": "...",
      "odds": 1.75,
      "risk": "low",
      "confidence": 4,
      "reason": "..."
    }}
  ],
  "vip_bets": [
    {{
      "match": "...",
      "fixture_id": 67890,
      "tip": "...",
      "odds": 1.60,
      "risk": "medium",
      "confidence": 3,
      "reason": "..."
    }}
  ],
  "edu_tip": "Rövid 1 mondatos tanács..."
}}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=1300,
        temperature=0.6,
    )

    content = response.choices[0].message.content
    print("OpenAI raw válasz (első 500 karakter):")
    print((content or "")[:500])

    data = json.loads(content)

    # Tisztítás (dupla esély, BTTS), minimum tippdarabok beállítása
    data = _ensure_min_bets(data, trimmed)

    return data


# -----------------------------
# Fő belépési pont: generate_tips
# -----------------------------
def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fő belépési pont a main.py számára.
    Visszaadja:
      - telegram_public_text
      - telegram_vip_text
      - public_bets (nyers lista, mérlegszámításhoz)
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

        # FREE fallback
        lines_public: List[str] = []
        for i, m in enumerate(trimmed[:3], start=1):
            desc = _format_match_for_prompt(m)
            lines_public.append(
                f"{i}. Meccs: {desc}\n"
                f"   Tipp: Hazai győzelem (óvatos oddszal)."
            )

        public_body = (
            "\n\n".join(lines_public) if lines_public else "Ma kevés publikus lehetőség látszik."
        )

        public_text = (
            f"👑 SZELVÉNYKIRÁLY – FREE TIPPEK (fallback mód) 👑\n"
            f"({today})\n\n"
            "Technikai hiba miatt most egyszerűsített tippek érkeznek, részletes AI elemzés nélkül.\n\n"
            + public_body
            + "\n\n💰 Bankroll tipp: max 1–2% keret tétben, és mindig felelősen játssz."
        )

        # VIP fallback
        lines_vip: List[str] = []
        for i, m in enumerate(trimmed[:7], start=1):
            desc = _format_match_for_prompt(m)
            lines_vip.append(
                f"{i}. Meccs: {desc}\n"
                f"   Tipp: Hazai győzelem vagy óvatos gólpiac (kicsit bátrabb oddszal)."
            )

        vip_body = (
            "\n\n".join(lines_vip) if lines_vip else "Ma kevés VIP lehetőség látszik."
        )

        vip_text = (
            f"🔥 SZELVÉNYKIRÁLY VIP – FALLBACK SZELVÉNY 🔥\n"
            f"({today})\n\n"
            "Az AI elemzés most technikai okokból nem elérhető, ezért egyszerűbb, óvatos VIP ötleteket kapsz.\n\n"
            + vip_body
            + "\n\n💰 Bankroll tipp: VIP-ben se lépd túl a bankrollod 1–3%-át szelvényenként."
            + "\n\n🎓 Mini tanács: Technikai hiba esetén se erőltesd a játékot – a sportfogadás maradjon szórakozás."
        )

        # fallbacknél is adjunk vissza nyers listákat (fixture_id nélkül)
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
