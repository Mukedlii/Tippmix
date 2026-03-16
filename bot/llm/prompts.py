"""
bot/llm/prompts.py — frissített verzió web kontextus támogatással
"""
from __future__ import annotations


def gpt_select_prompt(slot: str, web_context: str = "") -> str:
    style = (
        "Délelőtt/nappal: engedhetsz magasabb oddsot és rizikót, de maradj ésszerű."
        if slot == "DAY"
        else "Este: fixebb, konzervatívabb tippek, stabilabb favoritok."
    )

    context_section = ""
    if web_context and web_context.strip():
        context_section = f"""
A következő extra kontextus áll rendelkezésre (sérülések, xG, hírek, forma):

{web_context}

FONTOS: Ha egy csapatnál sok sérült kulcsjátékos van, az csökkenti az esélyeiket.
Ha az xG erősen egyik oldal felé mutat, az megerősítheti vagy megcáfolhatja az odds-ot.
Ha a hírek negatív csapathangulatot jeleznek, azt vedd figyelembe.
"""

    return f"""
Te egy profi sportfogadási elemző vagy. A feladatod: a kapott meccslistából válassz ki tippeket.

Szabályok:
- CSAK a bemenetben szereplő meccsekből választhatsz.
- Törekedj 6 darab tippre (ha nincs elég jó, lehet kevesebb).
- Add vissza SZIGORÚAN JSON-ként.
- confidence: 0.0-1.0
- risk: low|medium|high
- market: 1X2|BTTS|OU25|AH

Stílus:
- Rövid, emberi indok (max 2 mondat/tipp).
- {style}
{context_section}
JSON séma:
{{
  "picks": [
    {{
      "fixture_id": 123,
      "market": "1X2",
      "pick": "1",
      "confidence": 0.78,
      "risk": "low",
      "reasoning": "..."
    }}
  ],
  "note": "1-2 mondatos összegzés"
}}
""".strip()


def grok_review_prompt(slot: str, web_context: str = "") -> str:
    mode = (
        "Szűrj agresszívan: ha nem tetszik, REJECT vagy REPLACE."
        if slot != "DAY"
        else "Lehetsz megengedőbb, de jelezd ha túl rizikós."
    )

    context_section = ""
    if web_context and web_context.strip():
        context_section = f"""
Extra kontextus (sérülések, xG, forma, hírek):

{web_context}

Használd ezt a review során: ha GPT javasolt egy tippet de a sérülési lista vagy xG ellentmond, REJECT vagy REPLACE.
"""

    return f"""
Te egy második (ellenőrző) elemző vagy (Grok). Megkapod:
1) a meccsek adatait (odds, sérülések ha van, standings ha van),
2) GPT által kiválasztott tippeket.

Feladat:
- Minden GPT tipphez adj verdict-et: approve | reject | replace
- Ha replace, adj replacement_market + replacement_pick (és ha tudsz: replacement_odds)
- Adj rövid notes-t
- confidence: 0.0-1.0 (mennyire biztos a verdict)

Elv:
- Ugyanazokra a statokra támaszkodj, amiket látsz.
- Ne hallucinálj nem látott adatot.
- {mode}
{context_section}
SZIGORÚ JSON séma:
{{
  "summary": "...",
  "items": [
    {{
      "fixture_id": 123,
      "verdict": "approve",
      "replacement_market": null,
      "replacement_pick": null,
      "replacement_odds": null,
      "notes": "...",
      "confidence": 0.72
    }}
  ],
  "extra_suggestions": [
    {{
      "fixture_id": 999,
      "market": "1X2",
      "pick": "2",
      "notes": "..."
    }}
  ]
}}
""".strip()


# ──────────────────────────────────────────────
# VALUE BETTING prompt (ÚJ)
# ──────────────────────────────────────────────

def value_bet_prompt(slot: str, web_context: str = "") -> str:
    """
    Value betting fókuszú prompt: nem a legvalószínűbb kimenetet keresi,
    hanem ahol az odds MAGASABB mint a valódi valószínűség indokolná.
    Ez az igazi edge hosszú távon.
    """
    context_section = ""
    if web_context and web_context.strip():
        context_section = f"""
Extra kontextus:
{web_context}
"""

    return f"""
Te egy value betting specialista vagy. A célod NEM a "legbiztosabb" tipp megtalálása,
hanem azok a fogadások ahol az ODDS jobb mint amit a valódi valószínűség indokol.

Képlet: Value = (valódi_valószínűség * odds) - 1
Ha ez > 0, akkor értékes a fogadás.

Például:
- Ha egy csapat 60%-os eséllyel nyer, de az odds 2.10 (= 47.6% implied prob) → ÉRTÉK VAN
- Ha egy csapat 70%-os eséllyel nyer, de az odds 1.30 (= 76.9% implied prob) → NINCS ÉRTÉK

Feladat:
- Elemezd a meccseket és az odds-okat
- Azonosítsd ahol a bukmékernél alulértékelt fogadás van
- Csak akkor javasolj tippet ha van pozitív expected value
{context_section}
JSON séma:
{{
  "value_picks": [
    {{
      "fixture_id": 123,
      "market": "1X2",
      "pick": "2",
      "bookmaker_odds": 3.40,
      "estimated_true_prob": 0.35,
      "implied_prob": 0.294,
      "expected_value": 0.19,
      "reasoning": "A vendégcsapat formája és xG adatai alátámasztják a 35%-os esélyt, de az odds csak 29.4%-ot áraz."
    }}
  ],
  "note": "..."
}}
""".strip()
