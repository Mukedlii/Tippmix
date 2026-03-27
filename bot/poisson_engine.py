import math
import os
from typing import Any, Dict, List, Optional, Tuple

from bot.storage.poisson_stats import (
    ensure_results_columns,
    team_goal_rates,
    league_goal_baseline,
)
from bot.deduplication import deduplicate_tips


def _defaults_base() -> Dict[str, float]:
    # sane global soccer averages
    return {"n": 0.0, "home_for": 1.35, "away_for": 1.10}


def _defaults_team() -> Dict[str, float]:
    return {"n": 0.0, "gf": 1.20, "ga": 1.20}


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_cdf(k: int, lam: float) -> float:
    # P(X <= k)
    return sum(_poisson_pmf(i, lam) for i in range(0, k + 1))


def _score_matrix(lam_home: float, lam_away: float, max_goals: int = 8) -> List[List[float]]:
    # P(H=i, A=j)
    ph = [_poisson_pmf(i, lam_home) for i in range(max_goals + 1)]
    pa = [_poisson_pmf(j, lam_away) for j in range(max_goals + 1)]
    return [[ph[i] * pa[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]


def _p_1x2(lam_home: float, lam_away: float) -> Tuple[float, float, float]:
    m = _score_matrix(lam_home, lam_away)
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    for i in range(len(m)):
        for j in range(len(m[i])):
            if i > j:
                p_home += m[i][j]
            elif i == j:
                p_draw += m[i][j]
            else:
                p_away += m[i][j]
    # tail mass beyond max_goals is ignored; acceptable for small lambdas
    s = p_home + p_draw + p_away
    if s > 0:
        return p_home / s, p_draw / s, p_away / s
    return 0.0, 0.0, 0.0


def _p_over(total_line: float, lam_total: float) -> float:
    # P(G > line)
    # supports 2.5, 3.5 ...
    k = int(math.floor(total_line))
    # if line=2.5 => need >=3 goals => 1 - P(G<=2)
    return max(0.0, 1.0 - _poisson_cdf(k, lam_total))


def _p_btts_yes(lam_home: float, lam_away: float) -> float:
    # 1 - P(H=0) - P(A=0) + P(H=0,A=0)
    p_h0 = math.exp(-lam_home)
    p_a0 = math.exp(-lam_away)
    return max(0.0, min(1.0, 1.0 - p_h0 - p_a0 + (p_h0 * p_a0)))


def _pick_markets(
    match: Dict[str, Any],
    lam_home: float,
    lam_away: float,
) -> List[Dict[str, Any]]:
    lam_total = max(0.0, lam_home + lam_away)
    p_home, p_draw, p_away = _p_1x2(lam_home, lam_away)

    out: List[Dict[str, Any]] = []

    # SAFE: prefer Under/BTTS-No when strong
    p_over25 = _p_over(2.5, lam_total)
    p_under25 = 1.0 - p_over25
    p_btts = _p_btts_yes(lam_home, lam_away)
    p_btts_no = 1.0 - p_btts

    # thresholds tunable via env
    safe_thr = float(os.getenv("TIPPMIX_SAFE_P_MIN", "0.58"))
    risk_thr = float(os.getenv("TIPPMIX_RISK_P_MIN", "0.54"))

    # 1X2 main result suggestion (like the original bot)
    best_1x2 = max(
        [("Hazai győzelem", p_home), ("Döntetlen", p_draw), ("Vendég győzelem", p_away)],
        key=lambda x: x[1],
    )
    best_pick, best_p = best_1x2

    # DNB alternative: only meaningful if main pick is home/away (not draw)
    p_decided = 1.0 - p_draw
    p_home_dnb = (p_home / p_decided) if p_decided > 1e-9 else 0.0
    p_away_dnb = (p_away / p_decided) if p_decided > 1e-9 else 0.0

    if best_pick in ("Hazai győzelem", "Vendég győzelem"):
        if best_pick == "Hazai győzelem":
            dnb_pick = "Hazai (döntetlen visszajár)"
            dnb_p = p_home_dnb
        else:
            dnb_pick = "Vendég (döntetlen visszajár)"
            dnb_p = p_away_dnb
        # store DNB as an alternative row (same shelf as 1X2)
        out.append({"market": "DNB", "line": None, "pick": dnb_pick, "p": dnb_p, "shelf": "SAFE" if best_p >= safe_thr else "RISK"})

    if best_p >= safe_thr:
        out.append({"market": "1X2", "line": None, "pick": best_pick, "p": best_p, "shelf": "SAFE"})
    elif best_p >= risk_thr:
        out.append({"market": "1X2", "line": None, "pick": best_pick, "p": best_p, "shelf": "RISK"})

    # Under/Over 2.5
    if p_under25 >= safe_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "2.5 alatt (max. 2 gól)", "p": p_under25, "shelf": "SAFE"})
    elif p_over25 >= safe_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "2.5 felett (min. 3 gól)", "p": p_over25, "shelf": "SAFE"})
    elif p_over25 >= risk_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "2.5 felett (min. 3 gól)", "p": p_over25, "shelf": "RISK"})
    elif p_under25 >= risk_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "2.5 alatt (max. 2 gól)", "p": p_under25, "shelf": "RISK"})

    # BTTS
    if p_btts_no >= safe_thr:
        out.append({"market": "BTTS", "line": None, "pick": "Legalább egy 0-n marad", "p": p_btts_no, "shelf": "SAFE"})
    elif p_btts >= safe_thr:
        out.append({"market": "BTTS", "line": None, "pick": "Mindkét csapat góloz", "p": p_btts, "shelf": "SAFE"})
    elif p_btts >= risk_thr:
        out.append({"market": "BTTS", "line": None, "pick": "Mindkét csapat góloz", "p": p_btts, "shelf": "RISK"})
    elif p_btts_no >= risk_thr:
        out.append({"market": "BTTS", "line": None, "pick": "Legalább egy 0-n marad", "p": p_btts_no, "shelf": "RISK"})

    # DNB already handled above as alternative to 1X2 (lines 106-114)
    # No need to duplicate here

    # attach ids
    for it in out:
        it["fixture_id"] = match.get("fixture_id")
        it["league_name"] = match.get("league_name")
        it["country_name"] = match.get("country_name")
        it["kickoff_local"] = match.get("kickoff_local")
        it["home_team"] = match.get("home_team")
        it["away_team"] = match.get("away_team")
        it["home_team_id"] = match.get("home_team_id")
        it["away_team_id"] = match.get("away_team_id")
        it["lam_home"] = lam_home
        it["lam_away"] = lam_away
        # Pass through odds from match
        it["odds"] = match.get("odds")
        it["odds_source"] = match.get("odds_source")

    return out


def _is_top_league(league_name: str) -> bool:
    s = (league_name or "").lower()
    keys = [
        "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
        "champions league", "uefa champions league",
        "europa league", "uefa europa league",
        "conference league", "uefa europa conference league",
        "eredivisie", "primeira liga", "scottish premiership",
        "fa cup", "copa del rey", "dfb pokal", "coppa italia",
        "segunda", "championship",
    ]
    return any(k in s for k in keys)


def _fmt_time_iso(dt: str) -> str:
    # best-effort: "2026-03-09T20:30:00+01:00" -> "20:30"
    try:
        if "T" in dt:
            tail = dt.split("T", 1)[1]
            return tail[:5]
    except Exception:
        pass
    return ""


def generate_poisson_tips(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates SAFE + RISK picks (OU/BTTS/DNB) without odds / without OpenAI."""

    ensure_results_columns()

    out_rows: List[Dict[str, Any]] = []
    for m in matches:
        hid = m.get("home_team_id")
        aid = m.get("away_team_id")
        lid = m.get("league_id")
        
        # TEMPORARY: Allow matches without IDs (use defaults) while historical data backfills
        # TODO: Remove this after backfill completes
        if hid is None or aid is None or lid is None:
            # Generate hash-based fake IDs from team/league names for fallback
            import hashlib
            home_name = m.get("home_team", "Unknown")
            away_name = m.get("away_team", "Unknown")
            league_name = m.get("league_name", "Unknown")
            
            hid = int(hashlib.md5(home_name.encode()).hexdigest()[:8], 16) % 1000000
            aid = int(hashlib.md5(away_name.encode()).hexdigest()[:8], 16) % 1000000
            lid = int(hashlib.md5(league_name.encode()).hexdigest()[:8], 16) % 1000
            
            m["home_team_id"] = hid
            m["away_team_id"] = aid
            m["league_id"] = lid

        # baselines from history
        # Try league_id first, fallback to league_name matching
        base_raw = league_goal_baseline(
            league_id=int(lid) if lid else None,
            league_name=m.get("league_name"),
            days=int(os.getenv("TIPPMIX_HIST_DAYS", "180"))
        )
        rates_h_raw = team_goal_rates(
            team_id=int(hid) if hid else None,
            team_name=m.get("home_team"),
            days=int(os.getenv("TIPPMIX_TEAM_DAYS", "120"))
        )
        rates_a_raw = team_goal_rates(
            team_id=int(aid) if aid else None,
            team_name=m.get("away_team"),
            days=int(os.getenv("TIPPMIX_TEAM_DAYS", "120"))
        )

        base = base_raw or _defaults_base()
        rates_h = rates_h_raw or _defaults_team()
        rates_a = rates_a_raw or _defaults_team()

        used_league_defaults = base_raw is None
        used_team_defaults = (rates_h_raw is None) or (rates_a_raw is None)

        # Simple multiplicative model around league avg
        lg_home_for = float(base.get("home_for", 1.35))
        lg_away_for = float(base.get("away_for", 1.10))

        # attack/defense factors
        h_att = float(rates_h.get("gf", 1.35)) / max(0.3, lg_home_for)
        h_def = float(rates_h.get("ga", 1.10)) / max(0.3, lg_away_for)
        a_att = float(rates_a.get("gf", 1.10)) / max(0.3, lg_away_for)
        a_def = float(rates_a.get("ga", 1.35)) / max(0.3, lg_home_for)

        home_adv = float(os.getenv("TIPPMIX_HOME_ADV_GOALS", "0.10"))

        lam_home = max(0.05, lg_home_for * h_att * a_def + home_adv)
        lam_away = max(0.05, lg_away_for * a_att * h_def)

        rows = _pick_markets(m, lam_home, lam_away)
        for r in rows:
            # attach data quality signals so the text layer can be honest
            try:
                r["n_league"] = int(base.get("n") or 0)
            except Exception:
                r["n_league"] = 0
            try:
                r["n_home"] = int(rates_h.get("n") or 0)
            except Exception:
                r["n_home"] = 0
            try:
                r["n_away"] = int(rates_a.get("n") or 0)
            except Exception:
                r["n_away"] = 0
            r["used_league_defaults"] = bool(used_league_defaults)
            r["used_team_defaults"] = bool(used_team_defaults)
        out_rows.extend(rows)

    # rank by probability (descending), SAFE first
    safe_all = [r for r in out_rows if r.get("shelf") == "SAFE"]
    risk_all = [r for r in out_rows if r.get("shelf") == "RISK"]
    safe_all.sort(key=lambda x: float(x.get("p") or 0), reverse=True)
    risk_all.sort(key=lambda x: float(x.get("p") or 0), reverse=True)

    # VIP: prioritize top leagues for readability/stability
    safe_top = [r for r in safe_all if _is_top_league(str(r.get("league_name") or ""))]
    risk_top = [r for r in risk_all if _is_top_league(str(r.get("league_name") or ""))]
    safe_other = [r for r in safe_all if r not in safe_top]
    risk_other = [r for r in risk_all if r not in risk_top]

    max_safe = int(os.getenv("TIPPMIX_SAFE_COUNT", "8"))
    max_risk = int(os.getenv("TIPPMIX_RISK_COUNT", "6"))

    safe = (safe_top + safe_other)[:max_safe]
    risk = (risk_top + risk_other)[:max_risk]

    # Fallback: if thresholds were too strict, still emit some picks (better UX for subscribers)
    if not safe and not risk:
        fallback_min_p = float(os.getenv("TIPPMIX_FALLBACK_MIN_P", "0.50"))
        max_fb = int(os.getenv("TIPPMIX_FALLBACK_COUNT", "8"))
        all_rows = sorted(out_rows, key=lambda x: float(x.get("p") or 0), reverse=True)
        fb = [r for r in all_rows if float(r.get("p") or 0) >= fallback_min_p][:max_fb]
        # mark as RISK to be honest internally, but don't shout "NO BET"
        for r in fb:
            r["shelf"] = r.get("shelf") or "RISK"
        risk = fb

    def _conf_label(p01: float, dq: str) -> str:
        # premium, simple confidence label
        # data quality can cap confidence
        if dq == "low":
            if p01 >= 0.62:
                return "Közepes"
            return "Alacsony"
        if p01 >= 0.68:
            return "Magas"
        if p01 >= 0.58:
            return "Közepes"
        return "Alacsony"

    def _pick_display(mkt: str, pick: str) -> str:
        mkt = (mkt or "").upper().strip()
        pu = (pick or "").upper()
        if mkt == "OU" and "UNDER" in pu:
            return "Gólok alatt 2.5 (max 2 gól)"
        if mkt == "OU" and "OVER" in pu:
            return "Gólok felett 2.5 (min 3 gól)"
        if mkt == "BTTS" and "NO" in pu:
            return "Mindkét csapat gólt szerez: NEM"
        if mkt == "BTTS" and "YES" in pu:
            return "Mindkét csapat gólt szerez: IGEN"
        return pick

    def _dir_and_reason(r: Dict[str, Any]) -> tuple[str, str]:
        """Return (direction, short_reason)."""
        mkt = str(r.get("market") or "").upper().strip()
        pick = str(r.get("pick") or "").strip()
        ht = str(r.get("home_team") or "")
        at = str(r.get("away_team") or "")
        try:
            lh = float(r.get("lam_home") or 0.0)
            la = float(r.get("lam_away") or 0.0)
        except Exception:
            lh = la = 0.0

        # Winner-ish direction
        if mkt in ("1X2", "DNB"):
            if "Hazai" in pick or pick.lower().startswith("home"):
                return "Hazai oldal", f"A {ht} felé billen a meccs képe."
            if "Vendég" in pick or pick.lower().startswith("away"):
                return "Vendég oldal", f"A {at} erősebbnek tűnik ezen a párosításon."
            if "Döntetlen" in pick or "draw" in pick.lower():
                return "Döntetlen közeli", "Szoros meccsnek néz ki, döntetlen sem kizárt."
            # fallback to lambdas
            if lh > la + 0.15:
                return "Hazai oldal", f"A {ht} felé billen a meccs."
            if la > lh + 0.15:
                return "Vendég oldal", f"A {at} felé billen a meccs."
            return "Szoros meccs", "Kiegyenlített erőviszonyok látszanak."

        if mkt == "OU":
            if "Under" in pick or "alatt" in pick.lower():
                return "Kevés gól", "Óvatos, szoros meccskép várható."
            return "Sok gól", "Nyíltabb meccskép, több helyzet várható."

        if mkt == "BTTS":
            if "NO" in pick.upper() or "NEM" in pick.upper():
                return "Kevés gól / óvatos", "Legalább az egyik oldal könnyen beragadhat 0 gólra."
            return "Mindkét csapat gólt szerez", "Mindkét oldalon benne van a gól."

        return "Fő irány", "A modell szerint ez a legjobb értékű opció."

    def _dq_en(r: Dict[str, Any]) -> str:
        return str(r.get("data_quality") or "medium").lower()

    def fmt_tip(i: int, r: Dict[str, Any]) -> str:
        p01 = float(r.get("p") or 0.0)
        ht = str(r.get("home_team") or "")
        at = str(r.get("away_team") or "")
        league = str(r.get("league_name") or "")
        country = str(r.get("country_name") or "")
        ko = str(r.get("kickoff_local") or "")
        time_txt = _fmt_time_iso(ko)

        mkt = str(r.get("market") or "").upper().strip()
        pick = _pick_display(mkt, str(r.get("pick") or "").strip())

        dq = _dq_en(r)
        conf = _conf_label(p01, dq)
        direction, reason = _dir_and_reason(r)

        parts: List[str] = []
        parts.append("━━━━━━━━━━━━━━━━━━━━━━")
        parts.append(f"🔢 *TIPP #{i}*")
        parts.append(f"🏆 Liga: {league} – {country}" if country else f"🏆 Liga: {league}")
        parts.append(f"⚽ *{ht}* 🆚 *{at}*")
        parts.append(f"🕒 {time_txt}")
        parts.append(f"🎯 Fő irány: *{direction}*")
        parts.append(f"✅ Ajánlott tipp: *{pick}*")
        parts.append(f"🔥 Bizalom: *{conf}*")
        parts.append(f"📝 Indok: {reason}")

        if dq == "low":
            parts.append("⚠️ Adatbiztonság: alacsony")

        return "\n".join(parts)

    # Header
    date_disp = ""
    if matches:
        ko0 = str(matches[0].get("kickoff_local") or "")
        if "T" in ko0:
            date_disp = ko0.split("T", 1)[0]
    vip_lines: List[str] = []
    vip_lines.append(f"🏆 *NAPI TIPP CSOMAG – {date_disp or ''}*")
    vip_lines.append(f"📊 Mai kiemelt meccsek: {len(matches or [])}")
    vip_lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # VIP graceful degradation controls
    vip_allow_defaults = (os.getenv("TIPPMIX_VIP_ALLOW_DEFAULTS") or "1").strip() != "0"  # stage-3
    vip_allow_partial = (os.getenv("TIPPMIX_VIP_ALLOW_PARTIAL_DEFAULTS") or "1").strip() != "0"  # stage-2
    vip_min_real = int(os.getenv("TIPPMIX_VIP_MIN_REAL", os.getenv("TIPPMIX_MIN_VIP", "6")))
    vip_max_fallback = int(os.getenv("TIPPMIX_VIP_MAX_FALLBACK", "4"))

    def _is_real_data_row(r: Dict[str, Any]) -> bool:
        return (not bool(r.get("used_team_defaults"))) and (not bool(r.get("used_league_defaults")))

    def _is_partial_row(r: Dict[str, Any]) -> bool:
        # league baseline real but some team default(s), OR borderline team sample even if one side weak
        used_league_defaults = bool(r.get("used_league_defaults"))
        used_team_defaults = bool(r.get("used_team_defaults"))
        if (not used_league_defaults) and used_team_defaults:
            return True
        # If league baseline is real and at least one side has some history, accept as partial.
        try:
            n_home = int(r.get("n_home") or 0)
            n_away = int(r.get("n_away") or 0)
            n_league = int(r.get("n_league") or 0)
        except Exception:
            n_home = n_away = n_league = 0
        if (not used_league_defaults) and n_league >= 8 and max(n_home, n_away) >= 3 and min(n_home, n_away) < int(os.getenv("TIPPMIX_TEAM_MIN_N", "6")):
            return True
        return False

    def _vip_stage(r: Dict[str, Any]) -> int:
        if _is_real_data_row(r):
            return 1
        if vip_allow_partial and _is_partial_row(r):
            return 2
        if vip_allow_defaults:
            return 3
        return 99

    # Build per-fixture tips: main 1X2 + alternative DNB (same side)
    by_fixture: Dict[Any, Dict[str, Any]] = {}
    for r in (safe + risk):
        st = _vip_stage(r)
        if st >= 99:
            continue

        fid = r.get("fixture_id")
        if fid is None:
            continue
        box = by_fixture.setdefault(fid, {"base": r, "main": None, "alt": None})
        if (r.get("market") or "").upper() == "1X2":
            box["main"] = r
        elif (r.get("market") or "").upper() == "DNB":
            box["alt"] = r
        else:
            if not box.get("base"):
                box["base"] = r

    items = list(by_fixture.values())

    def _best_row(it: Dict[str, Any]) -> Dict[str, Any]:
        return it.get("main") or it.get("base") or {}

    # Ranking priority:
    # real+top, real+other, partial+top, partial+other, fallback+top, fallback+other (then p)
    def _vip_sort_key(it: Dict[str, Any]) -> tuple:
        r = _best_row(it)
        p = float(r.get("p") or 0.0)
        is_top = _is_top_league(str(r.get("league_name") or ""))
        st = _vip_stage(r)
        stage_score = 3 if st == 1 else (2 if st == 2 else 1)
        top_score = 1 if is_top else 0
        return (stage_score, top_score, p)

    items.sort(key=_vip_sort_key, reverse=True)

    # Stage selection with controlled fallback + anti-spam de-dup
    def _sig_for_row(r: Dict[str, Any]) -> tuple:
        # Collapse near-duplicates from default lambdas
        try:
            lh = round(float(r.get("lam_home") or 0.0), 2)
            la = round(float(r.get("lam_away") or 0.0), 2)
        except Exception:
            lh, la = 0.0, 0.0
        return (
            str(r.get("market") or "").upper(),
            str(r.get("pick") or ""),
            lh,
            la,
            bool(r.get("used_team_defaults")),
            bool(r.get("used_league_defaults")),
        )

    selected: List[Dict[str, Any]] = []
    seen_sigs: set = set()
    seen_fixtures: set = set()
    fallback_used = 0
    real_used = 0

    def _fixture_sig(r: Dict[str, Any]) -> tuple:
        # Prevent same match appearing multiple times (provider duplicates / multi-market rows)
        hid = r.get("home_team_id")
        aid = r.get("away_team_id")
        if hid is not None and aid is not None:
            return ("id", int(hid), int(aid), str(r.get("kickoff_local") or ""))
        return (
            "name",
            str(r.get("home_team") or "").strip().lower(),
            str(r.get("away_team") or "").strip().lower(),
            str(r.get("kickoff_local") or ""),
            str(r.get("league_name") or "").strip().lower(),
        )

    for it in items:
        r = _best_row(it)
        st = _vip_stage(r)
        if st == 99:
            continue

        # Full fallback (stage-3) strict conditions
        if st == 3:
            if fallback_used >= vip_max_fallback:
                continue
            if not _is_top_league(str(r.get("league_name") or "")):
                continue

        fixture_sig = _fixture_sig(r)
        if fixture_sig in seen_fixtures:
            continue

        sig = _sig_for_row(r)
        if sig in seen_sigs:
            continue

        selected.append(it)
        seen_fixtures.add(fixture_sig)
        seen_sigs.add(sig)

        if st == 1:
            real_used += 1
        elif st == 3:
            fallback_used += 1

        # Stop early once we have enough (keep earlier max_total cap below)
        if len(selected) >= int(os.getenv("TIPPMIX_VIP_MATCH_COUNT", str(max_safe + max_risk))):
            break

    # Ensure we try to hit vip_min_real if possible by preferring stage-1 items first
    if real_used < vip_min_real:
        # selected is already globally sorted; no extra action needed (stage-1 are ahead).
        pass

    items = selected

    max_total = int(os.getenv("TIPPMIX_VIP_MATCH_COUNT", str(max_safe + max_risk)))
    items = items[:max_total]

    if not items:
        # do not collapse to empty unless literally nothing made it through (should be rare)
        vip_lines.append("Ma kevés a stabil adat; csak óvatos, alacsony bizalmú jelzések vannak.")
    else:
        for idx, it in enumerate(items, start=1):
            main = it.get("main") or it.get("base") or {}
            alt = it.get("alt")
            vip_lines.append(fmt_tip(idx, main))
            if alt and (alt.get("pick") != main.get("pick")):
                try:
                    p_alt = float(alt.get("p") or 0) * 100.0
                except Exception:
                    p_alt = 0.0
                vip_lines.append(f"💡 Alternatíva (biztonságosabb): *{alt.get('pick')}* (p≈{p_alt:.0f}%)")

    vip_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    vip_lines.append("⚠️ Tippjáték, nem garantált nyeremény.")
    admin = (os.getenv("TIPPMIX_ADMIN_USERNAME") or "").strip().lstrip("@")
    if admin:
        vip_lines.append(f"📩 Kérdés? @{admin}")

    vip_text = "\n".join(vip_lines).strip()

    # FREE: only a few picks (prefer SAFE, but fall back to best available)
    free_n = int(os.getenv("TIPPMIX_PUBLIC_SAFE_COUNT", "3"))
    free = safe[:free_n]
    if not free:
        free = (risk[:free_n])
    public_lines: List[str] = []
    public_lines.append(f"🏆 *NAPI TIPP CSOMAG – {date_disp or ''}*")
    public_lines.append(f"📊 Mai kiemelt meccsek: {len(free)}")
    public_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    if free:
        for idx, r in enumerate(free, start=1):
            public_lines.append(fmt_tip(idx, r))
    else:
        public_lines.append("Ma kevesebb a stabil jel, ezért rövidebb a lista.")
    public_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    public_lines.append("⚠️ Tippjáték, nem garantált nyeremény.")
    public_text = "\n".join(public_lines).strip()

    # Map to existing schema: vip_bets/public_bets
    def to_bet(r: Dict[str, Any], tier: str) -> Dict[str, Any]:
        used_team_defaults = bool(r.get("used_team_defaults"))
        used_league_defaults = bool(r.get("used_league_defaults"))
        n_league = int(r.get("n_league") or 0)
        n_home = int(r.get("n_home") or 0)
        n_away = int(r.get("n_away") or 0)

        if used_team_defaults or used_league_defaults:
            dq = "low"
        elif min(n_home, n_away) >= 8 and n_league >= 25:
            dq = "high"
        else:
            dq = "medium"

        # Extract odds from match data
        odds_dict = r.get("odds") or {}
        odds_estimate = None
        
        # Calculate odds estimate based on pick and market
        pick = r.get("pick", "")
        market = r.get("market", "")
        
        # Try to get odds from TheOddsAPI for special markets
        home_team = r.get("home_team", "")
        away_team = r.get("away_team", "")
        
        if market == "OU" and ("felett" in pick.lower() or "over" in pick.lower()):
            # Over/Under - Over
            try:
                from bot.providers.theoddsapi import get_over_under_for_match
                import os
                
                sport_keys_env = (os.getenv("ODDS_SPORT_KEYS") or "").strip()
                if sport_keys_env:
                    sport_keys = [x.strip() for x in sport_keys_env.split(",") if x.strip()]
                else:
                    sport_keys = []
                
                if sport_keys:
                    line = r.get("line", 2.5)
                    over_odds, under_odds = get_over_under_for_match(home_team, away_team, sport_keys, line)
                    if over_odds:
                        odds_estimate = over_odds
                        print(f"[OU_ODDS] Over {line} for {home_team} vs {away_team}: {over_odds}")
                    else:
                        print(f"[OU_ODDS] No Over odds found for {home_team} vs {away_team}")
                else:
                    print(f"[OU_ODDS] No sport keys configured!")
            except Exception as e:
                print(f"[OU_ODDS] ERROR: {repr(e)}")
                pass
        
        elif market == "OU" and ("alatt" in pick.lower() or "under" in pick.lower()):
            # Over/Under - Under
            try:
                from bot.providers.theoddsapi import get_over_under_for_match
                import os
                
                sport_keys_env = (os.getenv("ODDS_SPORT_KEYS") or "").strip()
                sport_keys = [x.strip() for x in sport_keys_env.split(",") if x.strip()] if sport_keys_env else []
                
                if sport_keys:
                    line = r.get("line", 2.5)
                    over_odds, under_odds = get_over_under_for_match(home_team, away_team, sport_keys, line)
                    if under_odds:
                        odds_estimate = under_odds
                        print(f"[OU_ODDS] Under {line} for {home_team} vs {away_team}: {under_odds}")
                    else:
                        print(f"[OU_ODDS] No Under odds found for {home_team} vs {away_team}")
                else:
                    print(f"[OU_ODDS] No sport keys configured!")
            except Exception as e:
                print(f"[OU_ODDS] ERROR: {repr(e)}")
                pass
        
        elif "Hazai" in pick or "Home" in pick:
            odds_estimate = odds_dict.get("1")
        elif "Vendég" in pick or "Away" in pick:
            odds_estimate = odds_dict.get("2")
        elif "Döntetlen" in pick or "Draw" in pick:
            odds_estimate = odds_dict.get("X")
        
        return {
            "fixture_id": r.get("fixture_id"),
            "selection": r.get("pick"),
            "tip": r.get("pick"),
            "confidence": float(r.get("p") or 0) * 5.0,  # scale to 0-5 for storage compat
            "risk_level": "alacsony" if r.get("shelf") == "SAFE" else "magas",
            "reason": f"Poisson λh={float(r.get('lam_home') or 0):.2f}, λa={float(r.get('lam_away') or 0):.2f}",
            "market": r.get("market"),
            "line": r.get("line"),
            "shelf": r.get("shelf"),
            "tier": tier,
            "odds_estimate": odds_estimate,  # ADD ODDS!
            "odds": odds_dict,  # Keep full odds dict too
            "odds_source": r.get("odds_source"),

            # data-quality fields for DB verification / long-term tracking
            "used_team_defaults": used_team_defaults,
            "used_league_defaults": used_league_defaults,
            "n_home": n_home,
            "n_away": n_away,
            "n_league": n_league,
            "data_quality": dq,
        }

    # VIP bets list: keep consistent with VIP staged policy
    def _is_allowed_vip_row_for_bets(r: Dict[str, Any]) -> bool:
        st = _vip_stage(r)
        if st == 1:
            return True
        if st == 2:
            return True
        if st == 3:
            # mirror strict stage-3 constraints
            if not _is_top_league(str(r.get("league_name") or "")):
                return False
            return True
        return False

    # DEDUPLICATE: 1 tip per match (highest confidence)
    vip_rows_for_bets = [r for r in (safe + risk) if _is_allowed_vip_row_for_bets(r)]
    vip_rows_for_bets = deduplicate_tips(vip_rows_for_bets)
    free = deduplicate_tips(free)
    
    vip_bets = [to_bet(r, "VIP") for r in vip_rows_for_bets]
    public_bets = [to_bet(r, "FREE") for r in free]

    return {
        "vip_bets": vip_bets,
        "public_bets": public_bets,
        "telegram_vip_text": vip_text,
        "telegram_public_text": public_text,
    }
