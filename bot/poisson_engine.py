import math
import os
from typing import Any, Dict, List, Optional, Tuple

from bot.storage.poisson_stats import (
    ensure_results_columns,
    team_goal_rates,
    league_goal_baseline,
)


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

    # 1X2 main result suggestion (like the original bot)
    best_1x2 = max(
        [("Hazai győzelem", p_home), ("Döntetlen", p_draw), ("Vendég győzelem", p_away)],
        key=lambda x: x[1],
    )
    best_pick, best_p = best_1x2
    if best_p >= safe_thr:
        out.append({"market": "1X2", "line": None, "pick": best_pick, "p": best_p, "shelf": "SAFE"})
    elif best_p >= risk_thr:
        out.append({"market": "1X2", "line": None, "pick": best_pick, "p": best_p, "shelf": "RISK"})

    # thresholds tunable via env
    safe_thr = float(os.getenv("TIPPMIX_SAFE_P_MIN", "0.58"))
    risk_thr = float(os.getenv("TIPPMIX_RISK_P_MIN", "0.54"))

    # Under/Over 2.5
    if p_under25 >= safe_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "Under 2.5", "p": p_under25, "shelf": "SAFE"})
    elif p_over25 >= safe_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "Over 2.5", "p": p_over25, "shelf": "SAFE"})
    elif p_over25 >= risk_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "Over 2.5", "p": p_over25, "shelf": "RISK"})
    elif p_under25 >= risk_thr:
        out.append({"market": "OU", "line": 2.5, "pick": "Under 2.5", "p": p_under25, "shelf": "RISK"})

    # BTTS
    if p_btts_no >= safe_thr:
        out.append({"market": "BTTS", "line": None, "pick": "BTTS: NO", "p": p_btts_no, "shelf": "SAFE"})
    elif p_btts >= safe_thr:
        out.append({"market": "BTTS", "line": None, "pick": "BTTS: YES", "p": p_btts, "shelf": "SAFE"})
    elif p_btts >= risk_thr:
        out.append({"market": "BTTS", "line": None, "pick": "BTTS: YES", "p": p_btts, "shelf": "RISK"})
    elif p_btts_no >= risk_thr:
        out.append({"market": "BTTS", "line": None, "pick": "BTTS: NO", "p": p_btts_no, "shelf": "RISK"})

    # DNB (winner without draw)
    p_decided = 1.0 - p_draw
    if p_decided > 0:
        p_home_dnb = p_home / p_decided
        p_away_dnb = p_away / p_decided
        if max(p_home_dnb, p_away_dnb) >= safe_thr:
            out.append({
                "market": "DNB",
                "line": None,
                "pick": "Home DNB" if p_home_dnb >= p_away_dnb else "Away DNB",
                "p": max(p_home_dnb, p_away_dnb),
                "shelf": "SAFE",
            })
        elif max(p_home_dnb, p_away_dnb) >= risk_thr:
            out.append({
                "market": "DNB",
                "line": None,
                "pick": "Home DNB" if p_home_dnb >= p_away_dnb else "Away DNB",
                "p": max(p_home_dnb, p_away_dnb),
                "shelf": "RISK",
            })

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
        if hid is None or aid is None or lid is None:
            continue

        # baselines from history
        base = league_goal_baseline(int(lid), days=int(os.getenv("TIPPMIX_HIST_DAYS", "180"))) or _defaults_base()
        rates_h = team_goal_rates(int(hid), days=int(os.getenv("TIPPMIX_TEAM_DAYS", "120"))) or _defaults_team()
        rates_a = team_goal_rates(int(aid), days=int(os.getenv("TIPPMIX_TEAM_DAYS", "120"))) or _defaults_team()

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

        out_rows.extend(_pick_markets(m, lam_home, lam_away))

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

    def _stars(p01: float) -> str:
        # map prob -> 1..5 stars
        if p01 >= 0.70:
            n = 5
        elif p01 >= 0.64:
            n = 4
        elif p01 >= 0.58:
            n = 3
        elif p01 >= 0.53:
            n = 2
        else:
            n = 1
        return "⭐" * n

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

    def _analysis_text(r: Dict[str, Any]) -> str:
        lam_h = float(r.get("lam_home") or 0)
        lam_a = float(r.get("lam_away") or 0)
        mkt = str(r.get("market") or "").upper()
        pick = str(r.get("pick") or "")
        # short, concrete, data-driven (no promises)
        s1 = f"Várható gólok: hazai λ={lam_h:.2f}, vendég λ={lam_a:.2f} (Poisson modell, historikus adatok alapján)."
        if mkt == "OU":
            s2 = "Az összgól valószínűség eloszlása alapján ez a line adja a legjobb kockázat/hozam arányt."
        elif mkt == "BTTS":
            s2 = "A modell szerint a gól nélküli szcenáriók (0 gól egyik oldalon) aránya ezt támogatja."
        elif mkt == "DNB":
            s2 = "Döntetlen kockázat csökkentése miatt DNB a stabilabb választás."
        else:
            s2 = "Az 1X2 esélyek közül ez a legnagyobb valószínűségű kimenet a modell szerint."
        s3 = "Fegyelmezett téttel (bankroll 1–3%) érdemes kezelni."
        return f"{s1} {s2} {s3}"

    def fmt_tip(i: int, r: Dict[str, Any]) -> str:
        p01 = float(r.get("p") or 0.0)
        p = p01 * 100.0
        ht = str(r.get("home_team") or "")
        at = str(r.get("away_team") or "")
        league = str(r.get("league_name") or "")
        ko = str(r.get("kickoff_local") or "")
        time_txt = _fmt_time_iso(ko)
        date_txt = ko.split("T", 1)[0] if "T" in ko else ""
        mkt = str(r.get("market") or "").upper().strip()
        pick = _pick_display(mkt, str(r.get("pick") or "").strip())

        odds_txt = "—"  # odds not used in this engine
        stars = _stars(p01)

        parts = []
        parts.append("━━━━━━━━━━━━━━━━━━━━━━")
        parts.append(f"🔢 *TIPP #{i}*")
        parts.append(f"🏟️ {league} – -")
        parts.append(f"⚽ *{ht}* 🆚 *{at}*")
        parts.append(f"📅 {date_txt} | 🕐 {time_txt}")
        parts.append(f"📌 Tipp: {mkt}")
        parts.append(f"💡 Ajánlott fogadás: *{pick}*")
        parts.append(f"📈 Odds: {odds_txt}")
        parts.append(f"🔥 Bizalom: {stars} (p≈{p:.0f}%)")
        parts.append(f"🧠 Elemzés: {_analysis_text(r)}")
        return "\n".join(parts)

    # Header
    date_disp = ""
    if matches:
        ko0 = str(matches[0].get("kickoff_local") or "")
        if "T" in ko0:
            date_disp = ko0.split("T", 1)[0]
    vip_lines: List[str] = []
    vip_lines.append(f"🏆 *NAPI TIPP CSOMAG – {date_disp or ''}*")
    vip_lines.append(f"📊 Mai elemzések: {len(matches)} mérkőzés")
    vip_lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # Build list: SAFE first then RISK, but numbered sequentially
    tips_for_msg: List[Dict[str, Any]] = []
    tips_for_msg.extend(safe)
    tips_for_msg.extend(risk)

    if not tips_for_msg:
        # extreme edge-case: no picks at all
        vip_lines.append("Ma kevés a feldolgozható adat a modellezéshez.")
    else:
        for idx, r in enumerate(tips_for_msg, start=1):
            vip_lines.append(fmt_tip(idx, r))

    vip_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    vip_lines.append("⚠️ *FELELŐSSÉG KIZÁRÁS:* A tippek elemzésen alapulnak, nem garantálnak nyereményt. Csak felelősen fogadj!")
    admin = (os.getenv("TIPPMIX_ADMIN_USERNAME") or "").strip().lstrip("@")
    if admin:
        vip_lines.append(f"📩 Kérdés? @{admin}")

    vip_text = "\n".join(vip_lines).strip()

    # FREE: only a few SAFE picks
    free_n = int(os.getenv("TIPPMIX_PUBLIC_SAFE_COUNT", "3"))
    free = safe[:free_n]
    public_lines: List[str] = []
    public_lines.append(f"🏆 *NAPI TIPP CSOMAG – {date_disp or ''}*")
    public_lines.append(f"📊 Mai elemzések: {len(matches)} mérkőzés")
    public_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    if free:
        for idx, r in enumerate(free, start=1):
            public_lines.append(fmt_tip(idx, r))
    else:
        public_lines.append("Ma kevés jel volt, ezért rövidebb a lista.")
    public_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    public_lines.append("⚠️ *FELELŐSSÉG KIZÁRÁS:* A tippek elemzésen alapulnak, nem garantálnak nyereményt.")
    public_text = "\n".join(public_lines).strip()

    # Map to existing schema: vip_bets/public_bets
    def to_bet(r: Dict[str, Any], tier: str) -> Dict[str, Any]:
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
        }

    vip_bets = [to_bet(r, "VIP") for r in (safe + risk)]
    public_bets = [to_bet(r, "FREE") for r in free]

    return {
        "vip_bets": vip_bets,
        "public_bets": public_bets,
        "telegram_vip_text": vip_text,
        "telegram_public_text": public_text,
    }
