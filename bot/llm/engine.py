from __future__ import annotations

import json
import os
from typing import Any

from .clients import make_openai_client, make_grok_client
from .models import TipPick, GrokReview, GrokReviewItem
from .prompts import gpt_select_prompt, grok_review_prompt


def _safe_json_loads(text: str) -> Any:
    """
    Laza JSON mentőöv: ha a modell köré ír szöveget, megpróbáljuk kivágni a JSON blokkot.
    """
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    # próbáljuk első { ... utolsó } között
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("Model did not return valid JSON.")


def gpt_select_picks(matches: list[dict[str, Any]], slot: str, n: int = 6) -> tuple[list[TipPick], str]:
    client = make_openai_client()
    model = os.getenv("OPENAI_MODEL", "gpt-5")

    prompt = gpt_select_prompt(slot)
    payload = {
        "slot": slot,
        "target_picks": n,
        "matches": matches,
    }

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Válaszolj kizárólag JSON-nal."},
            {"role": "user", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.6,
        max_tokens=1400,
    )

    content = resp.choices[0].message.content or ""
    data = _safe_json_loads(content)

    picks: list[TipPick] = []
    for p in data.get("picks", []):
        fixture_id = int(p["fixture_id"])
        m = next((x for x in matches if int(x.get("fixture_id", 0)) == fixture_id), None)
        if not m:
            continue
        odds = None
        # ha 1X2 és van odds: próbáljuk kinyerni
        if p.get("market") == "1X2" and isinstance(m.get("odds"), dict):
            odds = m["odds"].get(p.get("pick"))
        picks.append(
            TipPick(
                fixture_id=fixture_id,
                home_team=m.get("home_team", ""),
                away_team=m.get("away_team", ""),
                league_name=m.get("league_name", ""),
                kickoff_local=m.get("kickoff_local", ""),
                market=p.get("market", "1X2"),
                pick=str(p.get("pick", "")),
                odds=odds,
                confidence=float(p.get("confidence", 0.5)),
                risk=str(p.get("risk", "medium")),
                reasoning=str(p.get("reasoning", ""))[:400],
            )
        )

    note = str(data.get("note", "")).strip()
    return picks, note


def grok_review(matches: list[dict[str, Any]], gpt_picks: list[TipPick], slot: str) -> GrokReview:
    client = make_grok_client()
    model = os.getenv("GROK_MODEL", "grok-4")

    prompt = grok_review_prompt(slot)

    payload = {
        "slot": slot,
        "matches": matches,
        "gpt_picks": [p.__dict__ for p in gpt_picks],
    }

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Válaszolj kizárólag JSON-nal."},
            {"role": "user", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.3,
        max_tokens=1600,
    )

    content = resp.choices[0].message.content or ""
    data = _safe_json_loads(content)

    items: list[GrokReviewItem] = []
    for it in data.get("items", []):
        items.append(
            GrokReviewItem(
                fixture_id=int(it["fixture_id"]),
                verdict=str(it.get("verdict", "approve")),
                replacement_pick=it.get("replacement_pick"),
                replacement_market=it.get("replacement_market"),
                replacement_odds=it.get("replacement_odds"),
                notes=str(it.get("notes", ""))[:400],
                confidence=float(it.get("confidence", 0.5)),
            )
        )

    return GrokReview(
        summary=str(data.get("summary", "")).strip(),
        items=items,
        extra_suggestions=list(data.get("extra_suggestions", [])) if isinstance(data.get("extra_suggestions", []), list) else [],
    )


def build_consensus(
    matches: list[dict[str, Any]],
    gpt_picks: list[TipPick],
    review: GrokReview,
    slot: str,
) -> tuple[list[TipPick], str]:
    """
    Közös döntés:
    - strict: csak approve (+ replace-ek), reject kiesik
    - soft: approve marad, reject csak ha Grok nagyon biztos (confidence>=0.75), replace alkalmazható
    """
    mode = os.getenv("GROK_REVIEW_MODE", "strict").lower()
    strict = (mode == "strict") or (slot != "DAY")

    review_map = {i.fixture_id: i for i in review.items}

    final: list[TipPick] = []
    dropped: list[int] = []
    replaced: list[int] = []

    for p in gpt_picks:
        r = review_map.get(p.fixture_id)
        if not r:
            # ha nincs review sor (ritka), strictben inkább dobjuk este
            if strict:
                dropped.append(p.fixture_id)
                continue
            final.append(p)
            continue

        if r.verdict == "approve":
            final.append(p)
        elif r.verdict == "reject":
            if strict:
                dropped.append(p.fixture_id)
            else:
                # soft módban csak akkor dobjuk, ha Grok nagyon biztos
                if r.confidence >= 0.75:
                    dropped.append(p.fixture_id)
                else:
                    final.append(p)
        elif r.verdict == "replace":
            # csere: ugyanaz a meccs, más pick
            m = next((x for x in matches if int(x.get("fixture_id", 0)) == p.fixture_id), None)
            if not m:
                dropped.append(p.fixture_id)
                continue
            new_market = r.replacement_market or p.market
            new_pick = r.replacement_pick or p.pick

            odds = None
            if new_market == "1X2" and isinstance(m.get("odds"), dict):
                odds = m["odds"].get(new_pick)
            if r.replacement_odds is not None:
                odds = float(r.replacement_odds)

            final.append(
                TipPick(
                    fixture_id=p.fixture_id,
                    home_team=p.home_team,
                    away_team=p.away_team,
                    league_name=p.league_name,
                    kickoff_local=p.kickoff_local,
                    market=new_market,
                    pick=str(new_pick),
                    odds=odds,
                    confidence=max(0.4, min(0.95, (p.confidence + r.confidence) / 2)),
                    risk=p.risk,
                    reasoning=(p.reasoning + " | Grok: " + r.notes)[:400],
                )
            )
            replaced.append(p.fixture_id)

    info = f"Grok review: {review.summary}".strip()
    if dropped:
        info += f" | Dropped: {len(dropped)}"
    if replaced:
        info += f" | Replaced: {len(replaced)}"
    return final, info
