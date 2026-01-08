from __future__ import annotations

def gpt_select_prompt(slot: str) -> str:
    # slot pl: DAY / EVENING
    style = (
        "Délelőtt/nappal: engedhetsz magasabb oddsot és rizikót, de maradj ésszerű."
        if slot == "DAY"
        else "Este: fixebb, konzervatívabb tippek, stabilabb favoritok."
    )
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


def grok_review_prompt(slot: str) -> str:
    mode = (
        "Szűrj agresszívan: ha nem tetszik, REJECT vagy REPLACE."
        if slot != "DAY"
        else "Lehetsz megengedőbb, de jelezd ha túl rizikós."
    )
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
