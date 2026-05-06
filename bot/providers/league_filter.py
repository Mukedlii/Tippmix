"""
bot/providers/league_filter.py

Liga szűrő — kizárja az ismeretlen/egzotikus ligákat.

HOVA KELL TENNI: bot/providers/league_filter.py

HOGYAN MŰKÖDIK:
  is_allowed_league("South Africa Premier League") → False  (kizárva)
  is_allowed_league("Premier League")              → True   (engedélyezett)
"""

from __future__ import annotations

# ── Engedélyezett liga kulcsszavak (részleges egyezés is elég) ──────────────
WHITELIST_KEYWORDS = [
    # Anglia
    "premier league", "championship", "league one", "league two", "fa cup", "efl",
    # Németország
    "bundesliga", "2. bundesliga", "dfb",
    # Spanyolország
    "la liga", "laliga", "primera", "segunda", "copa del rey",
    # Olaszország
    "serie a", "serie b", "coppa italia",
    # Franciaország
    "ligue 1", "ligue 2", "coupe de france",
    # Portugália
    "primeira liga", "liga portugal", "taça de portugal",
    # Hollandia
    "eredivisie", "eerste divisie", "knvb",
    # Belgium
    "jupiler", "pro league", "first division a",
    # Skócia
    "scottish premiership", "spfl",
    # Törökország
    "süper lig", "super lig", "tff",
    # Görögország
    "super league", "greek",
    # Ausztria
    "bundesliga austria", "österreichische",
    # Svájc
    "super league switzerland", "swiss",
    # Csehország
    "fortuna liga", "czech",
    # Lengyelország
    "ekstraklasa",
    # Románia
    "superliga romania", "liga 1 romania",
    # Horvátország
    "hnl", "croatia",
    # Szerbia
    "super liga serbia",
    # Ukrajna
    "premier league ukraine", "ukrainian",
    # Oroszország
    "rpl", "russian premier",
    # Európai kupák
    "champions league", "europa league", "conference league", "uefa",
    # Nemzetközi
    "world cup", "euro", "nations league",
    # Magyar
    "otp bank liga", "nb i", "nb ii", "mol liga", "hungarian",
]

# ── Tiltott ország nevek ─────────────────────────────────────────────────────
BLOCKED_COUNTRIES = {
    "south africa", "nigeria", "ghana", "kenya", "tanzania", "ethiopia",
    "cameroon", "senegal", "ivory coast", "côte d'ivoire", "morocco",
    "egypt", "algeria", "tunisia", "sudan", "uganda", "zambia",
    "zimbabwe", "botswana", "namibia", "mozambique",
    "saudi arabia", "qatar", "uae", "kuwait", "bahrain", "oman",
    "iran", "iraq", "jordan", "lebanon", "syria",
    "india", "bangladesh", "pakistan", "sri lanka",
    "vietnam", "thailand", "indonesia", "malaysia", "philippines",
    "china", "myanmar", "cambodia", "laos",
    "venezuela", "ecuador", "bolivia", "peru", "paraguay",
    "colombia", "guatemala", "honduras", "el salvador", "costa rica",
    "panama", "cuba", "haiti", "dominican republic",
    "australia", "new zealand",
    "faroe islands", "gibraltar", "san marino", "andorra", "malta",
    "liechtenstein", "kosovo",
}

# ── Tiltott liga kulcsszavak ─────────────────────────────────────────────────
BLOCKED_KEYWORDS = [
    "south africa", "nigeria", "ghana", "kenya",
    "saudi", "qatar", "uae", "gulf",
    "india", "indian super", "i-league",
    "vietnam", "thai", "indonesia", "malaysia",
    "australia", "a-league",
    "mls reserve", "usl", "nisa",
    "youth", "u17", "u19", "u21", "u23", "reserve", "b team",
    "women", "feminine", "femmes", "frauen", "femenino",
    "friendly", "club friendly", "international friendly",
]


def is_allowed_league(
    league_name: str,
    country_name: str = "",
) -> bool:
    """
    Megvizsgálja, hogy egy liga engedélyezett-e.

    Args:
        league_name:  Liga neve (pl. "South Africa Premier League")
        country_name: Ország neve (pl. "South Africa") — opcionális

    Returns:
        True  → engedélyezett (tipp generálható)
        False → tiltott (ki kell szűrni)
    """
    league_lower = (league_name or "").lower().strip()
    country_lower = (country_name or "").lower().strip()

    # 1. Ország tiltólista
    if country_lower and any(blocked in country_lower for blocked in BLOCKED_COUNTRIES):
        return False

    # 2. Liga tiltó kulcsszavak
    if any(kw in league_lower for kw in BLOCKED_KEYWORDS):
        return False

    # 3. Ha ország is meg van adva és az tiltott (liga névben)
    if any(blocked in league_lower for blocked in BLOCKED_COUNTRIES):
        return False

    # 4. Whitelist ellenőrzés — ha megfelel → engedélyezett
    if any(kw in league_lower for kw in WHITELIST_KEYWORDS):
        return True

    # 5. Ha egyik sem → ismeretlen liga → KIZÁRVA
    return False


def filter_matches(matches: list, log_filtered: bool = True) -> list:
    """
    Szűri a meccslistát: csak ismert, engedélyezett ligák maradnak.

    Args:
        matches: Meccsek listája (dict-ek, 'league_name' és 'country_name' mezőkkel)
        log_filtered: Naplózza-e a kiszűrt meccseket

    Returns:
        Szűrt meccsek listája
    """
    import logging
    log = logging.getLogger(__name__)

    allowed = []
    filtered_out = []

    for m in matches:
        league = m.get("league_name") or m.get("league") or ""
        country = m.get("country_name") or m.get("country") or ""

        if is_allowed_league(league, country):
            allowed.append(m)
        else:
            filtered_out.append(f"{league} ({country})")

    if log_filtered and filtered_out:
        unique = list(set(filtered_out))[:10]
        log.info(f"Liga szűrő kizárt {len(filtered_out)} meccset: {unique}")

    return allowed


# ── Gyors teszt ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_cases = [
        ("Premier League", "England", True),
        ("Bundesliga", "Germany", True),
        ("La Liga", "Spain", True),
        ("Champions League", "Europe", True),
        ("OTP Bank Liga", "Hungary", True),
        ("South Africa Premier League", "South Africa", False),
        ("Nigerian Premier League", "Nigeria", False),
        ("Saudi Pro League", "Saudi Arabia", False),
        ("Indian Super League", "India", False),
        ("U21 Liga", "Germany", False),
        ("Women's Super League", "England", False),
    ]

    print("Liga szűrő teszt:")
    all_ok = True
    for league, country, expected in test_cases:
        result = is_allowed_league(league, country)
        status = "✅" if result == expected else "❌ HIBA"
        if result != expected:
            all_ok = False
        print(f"  {status} {league} ({country}): {result}")

    print(f"\n{'✅ Minden teszt OK!' if all_ok else '❌ Hibás tesztek vannak!'}")
