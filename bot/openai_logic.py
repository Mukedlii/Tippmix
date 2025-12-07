import os
import json
import datetime
from typing import Any, Dict, List

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Hány meccset adjunk át maximum az OpenAI-nak (token kímélés)
MAX_MATCHES_FOR_OPENAI = 40

# Cél darabszámok
PUBLIC_MIN_TIPS = 3
VIP_MIN_TIPS = 5


def _format_match_for_prompt(match: Dict[str, Any]) -> str:
    """
    Meccs objektumot rövid, szöveges sorra alakítjuk.
    Nem baj, ha nem tökéletes – a lényeg, hogy érthető legyen a modellnek.
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

    parts = [sport.capitalize(), f"{home} vs {away}"]
    if league or country:
        parts.append(f"{league} {country}".strip())
    if kickoff:
        parts.append(str(kickoff))

    return " | ".join(parts)


def _build_matches_prompt(matches: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, m in enumerate(matches, start=1):
        lines.append(f"{idx}. {_format_match_for_prompt(m)}")
    return "\n".join(lines)


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
    Logika:
      - nagyon alacsony odds (~1.40 alatt) lehet zöld, ha a bizalom is magas
      - 1.4–1.8 között többnyire közepes, ritkán zöld
      - 1.8 fölött SOHA nem zöld
      - 2.5 fölött mindig piros
    """
    try:
        c = int(conf)
    except Exception:
        c = 3

    if odds_float is None:
        # ha nincs odds, maradunk a sima confidence-alapú logikánál
        if c >= 4:
            return "low"
        if c <= 2:
            return "high"
        return "medium"

    o = odds_float

    # Nagyon alacsony odds: elvileg stabilabb
    if o <= 1.40:
        if c >= 4:
            return "low"     # zöld: kis odds + magas bizalom
        if c <= 2:
            return "medium"
        return "medium"

    # 1.40–1.80: általában közepes, néha enyhe kockázat
    if o <= 1.80:
        if c >= 4:
            return "medium"  # már ne legyen zöld
        if c <= 2:
            return "high"
        return "medium"

    # 1.80–2.50: inkább közepes/kockázatos
    if o <= 2.50:
        if c >= 4:
            return "medium"
        if c <= 2:
            return "high"
        return "medium"

    # 2.50 fölött: mindig kockázatosabb
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


def _build_public_text(data: Dict[str, Any]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    public_bets = data.get("public_bets") or []

    header = (
        f"👑 SZELVÉNYKIRÁLY – FREE TIPPEK MA ESTÉRE 👑\n"
        f"({today} – max 3 stabilabb tipp)\n\n"
        "Az alábbi meccsek a statisztika, forma és keretek alapján ígéretesek "
        "egy óvatosabb kombira:\n"
    )

    if not public_bets:
        body = "Ma kevés igazán stabil FREE lehetőséget találtunk, ezért inkább visszafogottan játssz. 🙂"
    else:
        lines: List[str] = []
        for i, bet in enumerate(public_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = bet.get("tip") or "Óvatos hazai / döntetlen nélkül"
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = bet.get("reason") or "Statisztika és forma alapján értelmes választás."
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
        body = "Ma kevés az igazán jó VIP kombinációs lehetőség – ilyenkor jobb a kisebb akció, mint az erőltetett nagy odds. 🤝"
        total_odds_line = ""
    else:
        lines: List[str] = []
        approx_total_odds = 1.0

        for i, bet in enumerate(vip_bets, start=1):
            match = bet.get("match") or "Ismeretlen meccs"
            tip = bet.get("tip") or "Hazai győzelem / gólpiac"
            odds = bet.get("odds")
            odds_float = _odds_to_float(odds)
            reason = bet.get("reason") or "Forma, statisztika és keret alapján jó esély mutatkozik."
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

        if approx_total_odds > 1.01:
            total_odds_line = (
                f"\n\n📊 VIP összodds (hozzávetőleges): kb. {approx_total_odds:.2f}\n"
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

    return header + body + total_odds_line + bankroll_hint + edu_block


def _build_simple_bet_from_match(match: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ha az AI nem ad elég tippet, mi gyártunk egy óvatos, 'stabil' jellegű sort,
    hogy mindig legyen valami lehetőség.
    """
    desc = _format_match_for_prompt(match)
    return {
        "match": desc,
        "tip": "Óvatos fogadás: hazai nem kap ki (1X) vagy 1.5 felett gól (óvatos tartomány).",
        "odds": 1.40,
        "confidence": 3,
        "reason": "Hazai pálya vagy jobb forma miatt óvatos, stabil jellegű tipp.",
    }


def _truncate_reason(reason: str, max_len: int = 220) -> str:
    """Ne legyenek végtelen hosszú magyarázatok – max ~2 mondat."""
    reason = reason or ""
    if len(reason) <= max_len:
        return reason
    return reason[: max_len - 3].rstrip() + "..."


def _ensure_min_bets(data: Dict[str, Any], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Gondoskodik róla, hogy mindig legyen legalább:
      - 3 FREE tipp
      - 5 VIP tipp (ha van elég meccs)
    Ha az AI üres vagy kevés tippet ad, mi töltjük fel óvatos tippekkel.
    Plusz kicsit kitakarítjuk a reason szövegeket.
    """
    public = data.get("public_bets") or []
    vip = data.get("vip_bets") or []

    # Reason-ek rövidítése
    for bet in public + vip:
        if "reason" in bet:
            bet["reason"] = _truncate_reason(str(bet.get("reason", "")))

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

    # VIP – töltsük fel 5-ig
    already_used_vip = {b.get("match") for b in vip}
    for m in matches:
        if len(vip) >= VIP_MIN_TIPS:
            break
        desc = _format_match_for_prompt(m)
        if desc in already_used_vip:
            continue
        bet = _build_simple_bet_from_match(m)
        vip.append(bet)
        already_used_vip.add(desc)

    data["public_bets"] = public
    data["vip_bets"] = vip
    return data


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

Feladatod:

1) FREE (public_bets):
   - Válaszd ki a legjobb LEGALÁBB 1 és legfeljebb 3 mérkőzést.
   - Itt inkább óvatosabb, stabilabb tippeket adj.
   - MEHETNEK dupla esély tippek is: pl. "Hazai vagy döntetlen (1X)", "Vendég vagy döntetlen (X2)".

2) VIP (vip_bets):
   - Válaszd ki a legjobb LEGALÁBB 5 és legfeljebb 7 mérkőzést.
   - Itt lehet bátrabb az odds, de NE adj dupla esély tippeket.
   - VIP-ben NE használj ilyeneket: "1X", "X2", "12".
   - VIP-be inkább konkrét piacokat adj:
        * "Hazai győzelem"
        * "Vendég győzelem"
        * "Over 2.5 gól"
        * "Mindkét csapat szerez gólt"
        * "Hazai 1.5 felett gól", stb.

3) Minden kiválasztott meccshez add meg:
   - match: rövid leírás pl. "Manchester United vs West Ham (Premier League, 20:00)"
   - tip: EGYÉRTELMŰ, KONKRÉT fogadási ötlet (pl. "Hazai győzelem", "Over 2.5 gól", "Hazai vagy döntetlen (1X)")
   - odds: reális decimális odd (pl. 1.75, 2.10), akár becsült érték – nem kell pontosan egyeznie bukmékerekkel
   - risk: low / medium / high (kockázat szintje) – ezt használhatod, de a kockázat színét én a confidence + odds alapján számolom.
   - confidence: 1–5 közötti szám, hogy mennyire bízol a tippedben
   - reason: maximum 1–2 mondatos indoklás (max ~220 karakter),
             forma, statisztika, hazai pálya, sérülések, motiváció, stb. alapján.

Fontos korlátozások:

- Ugyanaz a meccs a public_bets és vip_bets listában legfeljebb EGYSZER szerepelhet.
  Ha mégis mindkettőbe beteszed, akkor más típusú tippet adj rá (pl. FREE: 1X, VIP: hazai győzelem).
- Ne ismételd szó szerint ugyanazt az indoklást minden meccsnél, legyen természetes, de tömör.

4) Adj egy nagyon rövid, 1 mondatos oktató tippet is:
   - edu_tip: pl. "Ne emeld a tétet csak azért, mert az előző szelvény vesztett."

FORMÁTUM:

Kizárólag ÉRVÉNYES JSON-t adj vissza, minden egyéb szöveg nélkül!

Példa struktúra:

{{
  "public_bets": [
    {{
      "match": "...",
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
        temperature=0.6,  # kevésbé bohóckodjon
    )

    content = response.choices[0].message.content
    print("OpenAI raw válasz (első 500 karakter):")
    print((content or "")[:500])

    data = json.loads(content)

    # Biztosítsuk, hogy legyen elég tipp, és a reason-ök rendben legyenek
    data = _ensure_min_bets(data, trimmed)

    return data


def generate_tips(matches: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Fő belépési pont a main.py számára.
    Visszaadja:
      - telegram_public_text
      - telegram_vip_text
    Mindkettő kész, formázott üzenet Telegramra.
    """
    try:
        data = _call_openai_for_tips(matches)
        public_text = _build_public_text(data)
        vip_text = _build_vip_text(data)
        return {
            "telegram_public_text": public_text,
            "telegram_vip_text": vip_text,
        }
    except Exception as e:
        # Ha bármi gond van az OpenAI-val, ne dőljön össze a bot.
        print("HIBA az OpenAI hívás során, fallback logikát használunk.")
        print("Részletek:", repr(e))

        # Fallback: nagyon egyszerű, stat nélküli tippek az első meccsekből,
        # csak hogy mindig menjen ki valami – hangsúlyozzuk a kockázatot.
        today = datetime.date.today().strftime("%Y.%m.%d.")
        trimmed = matches[:10]

        lines_public: List[str] = []
        for i, m in enumerate(trimmed[:3], start=1):
            desc = _format_match_for_prompt(m)
            lines_public.append(
                f"{i}. Meccs: {desc}\n"
                f"Tipp: Óvatos hazai/döntetlen nélküli opció vagy gólpiac (1.20–1.70 körüli oddal)."
            )

        public_body = "\n\n".join(lines_public) if lines_public else "Ma kevés publikus lehetőség látszik."

        public_text = (
            f"👑 SZELVÉNYKIRÁLY – FREE TIPPEK (fallback mód) 👑\n"
            f"({today})\n\n"
            "Technikai hiba miatt most egyszerűsített tippek érkeznek, részletes AI elemzés nélkül.\n\n"
            + public_body
            + "\n\n💰 Bankroll tipp: max 1–2% keret tétben, és mindig felelősen játssz."
        )

        lines_vip: List[str] = []
        for i, m in enumerate(trimmed[:7], start=1):
            desc = _format_match_for_prompt(m)
            lines_vip.append(
                f"{i}. Meccs: {desc}\n"
                f"Tipp: Kombinálható hazai/over jellegű lehetőség, de mivel ez fallback mód, csak óvatosan!"
            )

        vip_body = "\n\n".join(lines_vip) if lines_vip else "Ma kevés VIP lehetőség látszik."

        vip_text = (
            f"🔥 SZELVÉNYKIRÁLY VIP – FALLBACK SZELVÉNY 🔥\n"
            f"({today})\n\n"
            "Az AI elemzés most technikai okokból nem elérhető, ezért egyszerűbb, óvatos VIP ötleteket kapsz.\n\n"
            + vip_body
            + "\n\n💰 Bankroll tipp: VIP-ben se lépd túl a bankrollod 1–3%-át szelvényenként."
            + "\n\n🎓 Mini tanács: Technikai hiba esetén se erőltesd a játékot – a sportfogadás maradjon szórakozás."
        )

        return {
            "telegram_public_text": public_text,
            "telegram_vip_text": vip_text,
        }
