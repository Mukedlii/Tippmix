import os
import json
import datetime
from typing import Any, Dict, List

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Hány meccset adjunk át maximum az OpenAI-nak (token kímélés)
MAX_MATCHES_FOR_OPENAI = 40

# Cél darabszámok
PUBLIC_MIN_TIPS = 3      # FREE csatorna
VIP_MIN_TIPS = 7         # VIP csatorna – 7 tipp, ebből 3 kiemelt


# -------------------------------------------------------------------
#  Meccsek formázása
# -------------------------------------------------------------------


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


# -------------------------------------------------------------------
#  Odds, kockázat, bizalom
# -------------------------------------------------------------------


def _odds_to_float(odds: Any) -> float | None:
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


def _derive_risk_level(conf: Any, odds_float: float | None) -> str:
    """
    Bizalom (1–5) + odds alapján állapítjuk meg a kockázat szintjét:
      - 'low'    -> zöld
      - 'medium' -> narancs
      - 'high'   -> piros
    """
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


def _risk_to_emoji(conf: Any, odds_float: float | None) -> str:
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


# -------------------------------------------------------------------
#  Tippek típusai (dupla esély, normalizálás)
# -------------------------------------------------------------------


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
      - 'hazai vagy döntetlen' -> 'Hazai győzelem'
      - 'vendég vagy döntetlen' -> 'Vendég győzelem'
    """
    t = (tip or "").lower()
    if ("hazai" in t and "döntetlen" in t) or "1x" in t:
        return "Hazai győzelem"
    if ("vendég" in t and "döntetlen" in t) or "x2" in t:
        return "Vendég győzelem"
    if "12" in t:
        return "Hazai győzelem"
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
    """Ne legyenek végtelen hosszú magyarázatok – max ~2 mondat + tisztítás."""
    reason = reason or ""
    if len(reason) > max_len:
        reason = reason[: max_len - 3].rstrip() + "..."
    return _clean_reason(reason)


def _normalize_tip(tip: str) -> str:
    """
    Eltünteti a homályos / 'vagy' típusú dolgokat.
      - Ha 'hazai győzelem' benne van -> 'Hazai győzelem'
      - Ha 'vendég győzelem' -> 'Vendég győzelem'
      - Ha 'gólpiac' szó szerepel -> töröljük a 'gólpiac' szót
      - Ha ' vagy ' van a tippben -> az első rész marad
    Így nem lesznek 'hazai győzelem vagy gólpiac' típusú félmondatok.
    """
    if not tip:
        return ""

    original = tip
    t_low = tip.lower()

    # direkt, egyértelmű 1X2 kimentése
    if "hazai győzelem" in t_low:
        return "Hazai győzelem"
    if "vendég győzelem" in t_low or "idegenbeli győzelem" in t_low:
        return "Vendég győzelem"
    if "döntetlen" in t_low and "vagy" not in t_low:
        return "Döntetlen"

    # 'vagy' utáni rész levágása
    if " vagy " in t_low:
        before = original.split(" vagy ")[0].strip()
        if before:
            tip = before
            t_low = tip.lower()

    # 'gólpiac' kiszedése (ha maradt)
    if "gólpiac" in t_low:
        tip = tip.replace("gólpiac", "").replace("Gólpiac", "").strip()

    # ha túl általános lett, hagyjuk az eredetit
    return tip if tip else original


# -------------------------------------------------------------------
#  FREE szöveg
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
            "Ma kevés igazán stabil FREE lehetőséget találtunk, ezért inkább "
            "visszafogottan játssz. 🙂"
        )
    else:
        lines: List[str] = []
        for i, bet in enumerate(public_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = _normalize_tip(bet.get("tip") or "Hazai győzelem")
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = _truncate_reason(
                bet.get("reason") or "Statisztika és forma alapján értelmes választás."
            )
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

    return header + body


# -------------------------------------------------------------------
#  VIP szöveg + 3 kiemelt meccs
# -------------------------------------------------------------------


def _build_vip_text(data: Dict[str, Any]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    vip_bets = data.get("vip_bets") or []
    edu_tip = data.get("edu_tip") or (
        "Soha ne fogadj nagyobb összeggel csak azért, mert az előző szelvény nyert vagy vesztett."
    )

    header = (
        f"🔥 SZELVÉNYKIRÁLY VIP – KIRÁLYI KOMBI MA ESTÉRE 🔥\n"
        f"({today} – 5–7 gondosan válogatott tipp, nagyobb összodds)\n\n"
        "Ezek a meccsek kombinálva erősebb, de még ésszerűen vállalható "
        "kockázatú VIP szelvényt adnak:\n"
    )

    if not vip_bets:
        body = (
            "Ma kevés az igazán jó VIP kombinációs lehetőség – ilyenkor jobb a "
            "kisebb akció, mint az erőltetett nagy odds. 🤝"
        )
        total_odds_line = ""
        highlight_block = ""
    else:
        # Ha az AI adott highlight mezőt, használjuk; különben mi választunk.
        has_highlight_flag = any("highlight" in b for b in vip_bets)

        highlight_indices: set[int]
        if has_highlight_flag:
            highlight_indices = {
                idx for idx, b in enumerate(vip_bets) if b.get("highlight")
            }
        else:
            scores: List[tuple[int, int, float]] = []
            for idx, bet in enumerate(vip_bets):
                try:
                    c = int(bet.get("confidence", 3))
                except Exception:
                    c = 3
                c = max(1, min(5, c))

                o = _odds_to_float(bet.get("odds"))
                if o is None:
                    o = 99.0

                # nagyobb confidence, kisebb odds előnyben
                scores.append((idx, -c, o))

            scores.sort(key=lambda t: (t[1], t[2]))
            highlight_indices = {idx for idx, _, _ in scores[:3]} if len(vip_bets) >= 3 else set()

        lines: List[str] = []
        approx_total_odds = 1.0

        for i, bet in enumerate(vip_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = _normalize_tip(bet.get("tip") or "Hazai győzelem / gólpiac")
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = _truncate_reason(
                bet.get("reason") or "Forma, statisztika és keret alapján jó esély mutatkozik."
            )
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

            is_highlight = (i - 1) in highlight_indices
            title_line = f"{i}. Meccs: {match}"
            if is_highlight:
                title_line += "  🔥 KIEMELT"

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

        if approx_total_odds > 1.01:
            total_odds_line = f"\n\n📊 VIP összodds (hozzávetőleges): kb. {approx_total_odds:.2f}"
        else:
            total_odds_line = ""

        # Kiemelt meccsek rövid összefoglalója
        if highlight_indices:
            summary_lines: List[str] = []
            for idx in sorted(highlight_indices):
                b = vip_bets[idx]
                m = b.get("match") or "Ismeretlen meccs"
                t = _normalize_tip(b.get("tip") or "Tipp hiányzik")
                o_raw = b.get("odds")
                if o_raw:
                    summary_lines.append(f"- {m} – Tipp: {t} (Odd: {o_raw})")
                else:
                    summary_lines.append(f"- {m} – Tipp: {t}")
            highlight_block = (
                "\n\n🎯 Kiemelt mérkőzések röviden:\n" + "\n".join(summary_lines)
            )
        else:
            highlight_block = ""

    edu_block = f"\n\n🎓 Napi mini tanács:\n{edu_tip}"

    return header + body + highlight_block + total_odds_line + edu_block


# -------------------------------------------------------------------
#  Fallback tippek építése
# -------------------------------------------------------------------


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
    VIP fallback tipp, SOHA nem dupla esély.
    Egyszerű, de egyértelmű piac: hazai győzelem.
    """
    desc = _format_match_for_prompt(match)
    return {
        "match": desc,
        "tip": "Hazai győzelem",
        "odds": 1.80,
        "confidence": 3,
        "reason": "Hazai pálya előnye és alapvetően erősebb keret miatt vállalható VIP tipp.",
    }


# -------------------------------------------------------------------
#  Minimális tipp darabszám biztosítása
# -------------------------------------------------------------------


def _ensure_min_bets(data: Dict[str, Any], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Gondoskodik róla, hogy mindig legyen legalább:
      - 3 FREE tipp
      - 7 VIP tipp (ha van elég meccs)

    Szabályok:
      - FREE-ben MINDEN dupla esélyt agresszívebb 1 / 2-re írunk át.
      - VIP-ben NINCS dupla esély: minden 1X / X2 / 12 típusú tippet eldobjuk,
        és fallback VIP tippekkel pótoljuk.
      - A végén minden tipp átmegy _normalize_tip-en, hogy ne maradjon 'vagy' / 'gólpiac'.
    """
    public = data.get("public_bets") or []
    vip = data.get("vip_bets") or []

    # Reason-ek rövidítése + tisztítása
    for bet in public + vip:
        if "reason" in bet:
            bet["reason"] = _truncate_reason(str(bet.get("reason", "")))

    # --- FREE: dupla esélyt agresszív 1/2-re írjuk át ---
    for bet in public:
        tip_old = str(bet.get("tip", ""))
        if _is_double_chance_tip(tip_old):
            bet["tip"] = _make_more_aggressive_tip(tip_old)

    # --- VIP: dupla esély TILOS, töröljük őket ---
    vip_filtered: List[Dict[str, Any]] = []
    for bet in vip:
        tip = str(bet.get("tip", ""))
        if _is_double_chance_tip(tip):
            continue
        vip_filtered.append(bet)
    vip = vip_filtered

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

    # NORMALIZÁLÁS: ne maradjon 'vagy', 'gólpiac'
    for bet in public + vip:
        bet["tip"] = _normalize_tip(str(bet.get("tip", "")))

    data["public_bets"] = public
    data["vip_bets"] = vip
    return data


# -------------------------------------------------------------------
#  OpenAI hívás
# -------------------------------------------------------------------


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

Az alábbi meccsek közül kell FREE és VIP tippeket választanod, több sportágból.
A meccsek listája (röviden):

{matches_text}

CÉL:
- Ne csak 'hazai győzelem' tippeket adj.
- Használj többféle piacot: 1X2, Over/Under gólok, Mindkét csapat szerez gólt (BTTS), ázsiai vagy európai hendikep, stb.
- Kerüld a homályos tippeket: NE legyen a tippekben 'gólpiac', 'vagy', 'hazai győzelem vagy gólpiac', stb.
- MINDIG EGY konkrét kimenet legyen egy tipp (pl. 'Hazai győzelem', 'Over 2.5 gól', 'Mindkét csapat szerez gólt').

1) FREE (public_bets):
   - Válaszd ki a legjobb LEGALÁBB 1 és legfeljebb 3 mérkőzést.
   - Itt inkább óvatosabb, stabilabb tippeket adj (általában alacsonyabb odds).

2) VIP (vip_bets):
   - Válaszd ki a legjobb LEGALÁBB 5 és legfeljebb 7 mérkőzést.
   - Itt lehet bátrabb az odds, de továbbra is ésszerű keretek között.
   - A vip_bets-ben jelöld ki a 3 legbiztosabb tippet 'highlight': true mezővel:
        * ezeknél legyen magasabb confidence (4–5),
        * lehetőleg 1.40–1.90 közötti odds.
   - A többi tippnél 'highlight': false vagy hagyhatod el a mezőt.

3) Minden kiválasztott meccshez add meg:
   - match: rövid leírás pl. "Manchester United vs West Ham (Premier League, 20:00) [ID=12345]"
   - fixture_id: a fenti sorban szereplő [ID=12345] értéke számként (ha van ilyen)
   - tip: EGYÉRTELMŰ, KONKRÉT fogadási ötlet (pl. "Hazai győzelem", "Over 2.5 gól", "Mindkét csapat szerez gólt")
   - odds: reális decimális odd (pl. 1.75, 2.10), akár becsült érték
   - risk: low / medium / high (kockázat szintje)
   - confidence: 1–5 közötti szám, hogy mennyire bízol a tippedben
   - reason: maximum 1–2 mondatos indoklás (max ~220 karakter),
             forma, statisztika, hazai pálya, sérülések, motiváció, stb. alapján.

Fontos korlátozások:

- Ugyanaz a meccs a public_bets és vip_bets listában legfeljebb EGYSZER szerepelhet.
- Ne ismételd szó szerint ugyanazt az indoklást minden meccsnél, legyen természetes, de tömör.
- A tip mezőben NE szerepeljen 'vagy' szó és 'gólpiac' kifejezés.

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
      "highlight": true,
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
        max_tokens=1500,
        temperature=0.6,
    )

    content = response.choices[0].message.content
    print("OpenAI raw válasz (első 500 karakter):")
    print((content or "")[:500])

    data = json.loads(content)

    data = _ensure_min_bets(data, trimmed)

    return data


# -------------------------------------------------------------------
#  Public API – tippek generálása
# -------------------------------------------------------------------


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

        # --- FREE fallback ---
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
        )

        # --- VIP fallback ---
        lines_vip: List[str] = []
        for i, m in enumerate(trimmed[:7], start=1):
            desc = _format_match_for_prompt(m)
            lines_vip.append(
                f"{i}. Meccs: {desc}\n"
                f"Tipp: Hazai győzelem (kicsit bátrabb oddszal)."
            )

        vip_body = (
            "\n\n".join(lines_vip) if lines_vip else "Ma kevés VIP lehetőség látszik."
        )

        vip_text = (
            f"🔥 SZELVÉNYKIRÁLY VIP – FALLBACK SZELVÉNY 🔥\n"
            f"({today})\n\n"
            "Az AI elemzés most technikai okokból nem elérhető, ezért "
            "egyszerűbb, óvatos VIP ötleteket kapsz.\n\n"
            + vip_body
            + "\n\n🎓 Mini tanács: A sportfogadás mindig kockázatos, kezeld szórakozásként."
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
