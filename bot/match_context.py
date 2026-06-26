"""
bot/match_context.py

Gazdagított meccs kontextus építő.

Kiterjeszti a meglévő bot/providers/web_context.py funkcionalitást:
  - Forma mátrix (utolsó 5 meccs eredmény)
  - xG trendek
  - Taktikai matchup összefoglaló
  - Meccs fontossági jelzők
  - Explicit AI instrukció: "Utasítsd el, ha a metrikák nem egyeznek az oddsokkal"

Visszaad egy strukturált kontextus szöveget ami az AI promptba kerül.

Használat:
    from bot.match_context import build_enhanced_context
    ctx = build_enhanced_context(home, away, league, match_data)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

ENABLE_WEB_CONTEXT = (os.getenv("ENABLE_WEB_CONTEXT") or "1").strip() == "1"


def _safe_form_str(form: List[str]) -> str:
    """Forma lista → emberi olvasható string."""
    if not form:
        return "N/A"
    symbols = []
    for r in form[:5]:
        r_upper = str(r).upper()
        if r_upper == "W":
            symbols.append("✅")
        elif r_upper == "D":
            symbols.append("➖")
        elif r_upper == "L":
            symbols.append("❌")
        else:
            symbols.append("❓")
    return " ".join(symbols)


def _form_summary(form: List[str]) -> str:
    """Forma összefoglaló szöveg."""
    if not form:
        return "Nincs adat"
    total = min(len(form), 5)
    wins = sum(1 for r in form[:5] if str(r).upper() == "W")
    draws = sum(1 for r in form[:5] if str(r).upper() == "D")
    losses = sum(1 for r in form[:5] if str(r).upper() == "L")
    pts = wins * 3 + draws
    max_pts = total * 3
    pct = round(pts / max_pts * 100) if max_pts > 0 else 0
    return f"{wins}W {draws}D {losses}L ({pct}% pont)"


def _build_form_section(match: Dict[str, Any], home: str, away: str) -> str:
    """Forma szekció szöveg."""
    home_form = match.get("home_form") or []
    away_form = match.get("away_form") or []

    if not home_form and not away_form:
        return ""

    lines = ["📊 FORMA (utolsó 5 meccs):"]
    if home_form:
        lines.append(f"  {home}: {_safe_form_str(home_form)} → {_form_summary(home_form)}")
    if away_form:
        lines.append(f"  {away}: {_safe_form_str(away_form)} → {_form_summary(away_form)}")

    # Momentum összefoglaló
    if home_form and away_form:
        home_pts = sum(3 if str(r).upper() == "W" else (1 if str(r).upper() == "D" else 0) for r in home_form[:5])
        away_pts = sum(3 if str(r).upper() == "W" else (1 if str(r).upper() == "D" else 0) for r in away_form[:5])
        if home_pts > away_pts + 3:
            lines.append(f"  ⚡ Momentum: {home} erősen jobb formában")
        elif away_pts > home_pts + 3:
            lines.append(f"  ⚡ Momentum: {away} erősen jobb formában")
        else:
            lines.append("  ⚡ Momentum: Kiegyenlített")

    return "\n".join(lines)


def _build_xg_section(match: Dict[str, Any], home: str, away: str) -> str:
    """xG szekció szöveg."""
    xg_home = match.get("xg_home")
    xg_away = match.get("xg_away")

    if xg_home is None and xg_away is None:
        return ""

    lines = ["⚽ xG TELJESÍTMÉNY (utolsó meccsek átlaga):"]
    if xg_home is not None:
        lines.append(f"  {home} xG: {xg_home:.2f}")
    if xg_away is not None:
        lines.append(f"  {away} xG: {xg_away:.2f}")

    if xg_home is not None and xg_away is not None:
        diff = xg_home - xg_away
        if diff >= 0.5:
            lines.append(f"  📈 {home} szignifikánsan jobb xG-vel rendelkezik (+{diff:.2f})")
        elif diff <= -0.5:
            lines.append(f"  📈 {away} szignifikánsan jobb xG-vel rendelkezik ({diff:.2f})")
        else:
            lines.append(f"  ↔️ Kiegyenlített xG különbség ({diff:+.2f})")

    return "\n".join(lines)


def _build_injury_section(match: Dict[str, Any], home: str, away: str) -> str:
    """Sérülés szekció szöveg."""
    injuries = match.get("injuries") or []
    if not injuries:
        return ""

    lines = [f"🏥 SÉRÜLÉSEK ({len(injuries)} játékos érintett):"]
    for inj in injuries[:6]:
        player = inj.get("player") or inj.get("name") or "Ismeretlen"
        team = inj.get("team") or ""
        reason = inj.get("reason") or inj.get("injury") or ""
        lines.append(f"  - {player} ({team}): {reason}")

    if len(injuries) > 6:
        lines.append(f"  ... és még {len(injuries) - 6} sérült")

    return "\n".join(lines)


def _build_h2h_section(match: Dict[str, Any], home: str, away: str) -> str:
    """H2H szekció szöveg."""
    h2h = match.get("h2h")
    if not h2h:
        return ""

    if isinstance(h2h, dict):
        hw = h2h.get("home_wins", 0) or 0
        aw = h2h.get("away_wins", 0) or 0
        dr = h2h.get("draws", 0) or 0
        total = hw + aw + dr
        if total == 0:
            return ""
        lines = [
            f"📋 H2H (egymás elleni mérkőzések, {total} meccs):",
            f"  {home} győzelem: {hw}",
            f"  Döntetlen: {dr}",
            f"  {away} győzelem: {aw}",
        ]
        return "\n".join(lines)

    if isinstance(h2h, list) and len(h2h) > 0:
        total = len(h2h)
        hw = sum(1 for g in h2h if str(g.get("winner", "")).lower() == "home")
        aw = sum(1 for g in h2h if str(g.get("winner", "")).lower() == "away")
        dr = total - hw - aw
        lines = [
            f"📋 H2H ({total} meccs):",
            f"  {home}: {hw}, Döntetlen: {dr}, {away}: {aw}",
        ]
        return "\n".join(lines)

    return ""


def _build_odds_context(match: Dict[str, Any]) -> str:
    """Odds kontextus szöveg — AI instrukció a metrika-odds összevetéshez."""
    odds = match.get("odds") or match.get("scraped_odds") or {}
    if not odds:
        return ""

    lines = ["💰 AKTUÁLIS ODDSZOK:"]
    try:
        o1 = odds.get("1")
        ox = odds.get("X")
        o2 = odds.get("2")
        if o1:
            lines.append(f"  Hazai győzelem (1): {float(o1):.2f}")
        if ox:
            lines.append(f"  Döntetlen (X): {float(ox):.2f}")
        if o2:
            lines.append(f"  Vendég győzelem (2): {float(o2):.2f}")
    except (TypeError, ValueError):
        return ""

    return "\n".join(lines)


def _build_tournament_section(match: Dict[str, Any]) -> str:
    """Torna kontextus szöveg (ha van)."""
    label = match.get("tournament_label") or ""
    if not label:
        return ""
    priority = match.get("tournament_priority") or 0
    return f"🏆 TORNA: {label} (prioritás: {priority}/10)"


def build_enhanced_context(
    home_team: str,
    away_team: str,
    league_name: str,
    match_data: Optional[Dict[str, Any]] = None,
    web_context_str: str = "",
) -> str:
    """
    Gazdagított kontextus szöveg az AI prompthoz.

    Tartalmaz:
      - Torna információ
      - Forma mátrix
      - xG összehasonlítás
      - Sérülés lista
      - H2H statisztika
      - Odds kontextus
      - AI instrukció: "Utasítsd el, ha a metrikák nem egyeznek az oddsokkal"

    Args:
        home_team:       Hazai csapat neve
        away_team:       Vendég csapat neve
        league_name:     Liga neve
        match_data:      Meccs dict (opcionális, extra mezőkkel)
        web_context_str: Már meglévő web kontextus szöveg (opcionális)

    Returns:
        Kontextus szöveg string
    """
    m = match_data or {}
    sections: List[str] = []

    # Alap meccs fejléc
    sections.append(f"=== MECCS KONTEXTUS: {home_team} vs {away_team} ===")
    sections.append(f"Liga: {league_name}")

    # Torna info
    tournament_section = _build_tournament_section(m)
    if tournament_section:
        sections.append(tournament_section)

    # Meccs pontszám (ha van)
    score = m.get("match_score")
    if score is not None:
        sections.append(f"📊 Meccs minőségi pontszám: {score:.1f}/10")

    # Forma
    form_section = _build_form_section(m, home_team, away_team)
    if form_section:
        sections.append(form_section)

    # xG
    xg_section = _build_xg_section(m, home_team, away_team)
    if xg_section:
        sections.append(xg_section)

    # Sérülések
    injury_section = _build_injury_section(m, home_team, away_team)
    if injury_section:
        sections.append(injury_section)

    # H2H
    h2h_section = _build_h2h_section(m, home_team, away_team)
    if h2h_section:
        sections.append(h2h_section)

    # Odds
    odds_section = _build_odds_context(m)
    if odds_section:
        sections.append(odds_section)

    # Meglévő web kontextus beillesztése (ha van)
    if web_context_str and web_context_str.strip():
        sections.append("🌐 WEB KONTEXTUS:")
        sections.append(web_context_str.strip())

    # AI instrukció — KRITIKUS RÉSZ
    sections.append(
        "⚠️ AI INSTRUKCIÓ: "
        "Ha a fenti metrikák (forma, xG, sérülések) NEM támasztják alá az oddsokat, "
        "UTASÍTSD EL ezt a meccset. Csak olyan meccset ajánlj, ahol az elemzés és az "
        "oddszok ÖSSZHANGBAN vannak. Magas oddszokhoz erős statisztikai alap kell."
    )

    return "\n\n".join(s for s in sections if s.strip())


def build_context_for_prompt_batch(
    matches: List[Dict[str, Any]],
    web_contexts: Optional[Dict[Any, str]] = None,
    max_matches: int = 10,
) -> str:
    """
    Több meccs kontextusát építi össze egyetlen prompt szöveggé.

    Args:
        matches:      Meccsek listája (match_score-ral rendezve ajánlott)
        web_contexts: Dict(fixture_id → web kontextus szöveg) — opcionális
        max_matches:  Maximum meccs kontextusok száma

    Returns:
        Összes meccs kontextusa összefűzve
    """
    if web_contexts is None:
        web_contexts = {}

    parts: List[str] = []

    for m in matches[:max_matches]:
        home = m.get("home_team") or ""
        away = m.get("away_team") or ""
        league = m.get("league_name") or ""
        fid = m.get("fixture_id")

        web_ctx = web_contexts.get(fid, "")

        ctx = build_enhanced_context(
            home_team=home,
            away_team=away,
            league_name=league,
            match_data=m,
            web_context_str=web_ctx,
        )
        parts.append(ctx)

    separator = "\n\n" + "─" * 60 + "\n\n"
    return separator.join(parts)
