import datetime
from typing import Any, Dict, List, Optional

import requests

from bot.api_keys import get_api_sports_key, resolve_sports_provider
from bot.providers import sportsdataio, sportmonks, allsportsapi


def _normalize_fixture_id(fixture_id_value: Any, match_text: Optional[str] = None) -> Optional[int]:
    """
    Kinyeri a numerikus fixture ID-t több formából:
      - 1488772
      - "1488772"
      - "football-1488772"
      - match szöveg végéről: "... [ID=football-1488772]"
    """
    if fixture_id_value is not None:
        try:
            s = str(fixture_id_value).strip()
            if "-" in s:
                s = s.split("-")[-1]
            return int(s)
        except Exception:
            pass

    if match_text:
        text = str(match_text)
        marker = "[ID="
        if marker in text:
            tail = text.split(marker, 1)[1]
            if "]" in tail:
                tail = tail.split("]", 1)[0]
            try:
                if "-" in tail:
                    tail = tail.split("-")[-1]
                return int(tail)
            except Exception:
                pass

    return None


def _get_fixture_result(fixture_id: int) -> Dict[str, Any]:
    """
    Lekéri egy meccs (fixture) állapotát/eredményét.
    API-FOOTBALL (API-Sports) vagy SportsDataIO provider alapján.
    """
    provider = resolve_sports_provider()
    
    # Free scraper (SofaScore)
    if provider == "free_scraper":
        from bot.providers.free_fixtures import fetch_sofascore_result
        result = fetch_sofascore_result(fixture_id)
        if not result:
            return {}
        # Normalize to a common format
        return {
            "status": result.get("status"),
            "home_score": result.get("home_score"),
            "away_score": result.get("away_score"),
        }
    
    if provider == "sportsdataio":
        game = sportsdataio.fetch_game_by_id(fixture_id)
        return game or {}

    if provider == "sportmonks":
        # include scores so we can settle 1X2
        fx = sportmonks.get_fixture_by_id(fixture_id, include_scores=True)
        return fx or {}

    if provider == "allsportsapi":
        fx = allsportsapi.fixture_by_id(fixture_id)
        return fx or {}

    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": get_api_sports_key()}
    params = {"id": fixture_id}

    resp = requests.get(url, headers=headers, params=params, timeout=25)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("response"):
        return {}
    return data["response"][0]


def _settle_tip_1x2(tip: str, fixture: Dict[str, Any]) -> str:
    """
    Kifejezetten 1X2 piacra:
      - "Hazai győzelem"
      - "Döntetlen"
      - "Vendég győzelem"

    Vissza: "win" | "lose" | "pending" | "unknown"
    """
    if not fixture:
        return "unknown"

    # Free scraper (SofaScore) format
    if resolve_sports_provider() == "free_scraper":
        raw_status = (fixture.get("status") or "").upper()
        home_goals = fixture.get("home_score")
        away_goals = fixture.get("away_score")
        if raw_status not in ("FT", "FINISHED"):
            return "pending"
        if home_goals is None or away_goals is None:
            return "unknown"
        # Normalize status to FT for common logic below
        status = "FT"

    elif resolve_sports_provider() == "sportsdataio":
        status = (fixture.get("Status") or "").upper()
        home_goals = fixture.get("HomeTeamScore")
        away_goals = fixture.get("AwayTeamScore")
        if status not in ("FINAL", "FINAL/OT", "FINAL/SO", "FT"):
            return "pending"
    elif resolve_sports_provider() == "sportmonks":
        # state_id=5 => FT (SportMonks states)
        state_id = fixture.get("state_id")
        try:
            state_id = int(state_id)
        except Exception:
            state_id = None
        if state_id != 5:
            return "pending"

        # Scores include: pick CURRENT for home/away goals
        scores = fixture.get("scores") or []
        hg = ag = None
        for sc in scores:
            if (sc.get("description") or "").upper() != "CURRENT":
                continue
            score = sc.get("score") or {}
            part = (score.get("participant") or "").lower()
            goals = score.get("goals")
            try:
                goals = int(goals)
            except Exception:
                continue
            if part == "home":
                hg = goals
            elif part == "away":
                ag = goals
        home_goals, away_goals = hg, ag
        status = "FT" if state_id == 5 else ""
        if home_goals is None or away_goals is None:
            return "unknown"

    elif resolve_sports_provider() == "allsportsapi":
        st = (fixture.get("event_status") or "").strip()
        # examples: "Finished" or numeric live minute (e.g. "74")
        finished = st.lower() in ("finished", "ft")
        if not finished:
            # if final score not present, treat as pending
            if not fixture.get("event_final_result"):
                return "pending"

        score = str(fixture.get("event_final_result") or "").strip()
        home_goals = away_goals = None
        if "-" in score:
            try:
                a, b = [x.strip() for x in score.split("-", 1)]
                home_goals = int(a)
                away_goals = int(b)
            except Exception:
                home_goals = away_goals = None
        status = "FT" if finished else st
        if home_goals is None or away_goals is None:
            return "unknown"

    else:
        fx = fixture.get("fixture") or {}
        status = ((fx.get("status") or {}).get("short") or "").upper()

        goals = fixture.get("goals") or {}
        home_goals = goals.get("home")
        away_goals = goals.get("away")

    # még nem végleges (api-sports)
    if resolve_sports_provider() != "sportsdataio":
        if status not in ("FT", "AET", "PEN"):
            return "pending"

    if home_goals is None or away_goals is None:
        return "unknown"

    t = (tip or "").strip().lower()

    # 1X2 kimenet
    if "hazai győzelem" in t:
        return "win" if home_goals > away_goals else "lose"
    if "vendég győzelem" in t:
        return "win" if away_goals > home_goals else "lose"
    if "döntetlen" in t:
        return "win" if home_goals == away_goals else "lose"

    return "unknown"


def evaluate_bets(bets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Végigmegy a tippeken, visszaad egy összesítést:
      - total
      - win
      - lose
      - pending
      - unknown
      - details: list of {match, tip, result, score, status, fixture_id}
    """
    summary = {
        "total": 0,
        "win": 0,
        "lose": 0,
        "pending": 0,
        "unknown": 0,
        "details": [],
    }

    for bet in bets:
        raw_fixture_id = bet.get("fixture_id")
        match_text = bet.get("match")
        tip = bet.get("tip")

        fixture_id = _normalize_fixture_id(raw_fixture_id, match_text)

        fixture_data: Dict[str, Any] = {}
        result = "unknown"
        status = ""
        score = ""

        if not fixture_id:
            result = "unknown"
        else:
            try:
                fixture_data = _get_fixture_result(int(fixture_id))
                result = _settle_tip_1x2(tip, fixture_data)

                if resolve_sports_provider() == "sportsdataio":
                    status = (fixture_data.get("Status") or "").upper()
                    hg = fixture_data.get("HomeTeamScore")
                    ag = fixture_data.get("AwayTeamScore")
                    if isinstance(hg, int) and isinstance(ag, int):
                        score = f"{hg}–{ag}"
                else:
                    fx = fixture_data.get("fixture") or {}
                    status = ((fx.get("status") or {}).get("short") or "").upper()

                    goals = fixture_data.get("goals") or {}
                    hg = goals.get("home")
                    ag = goals.get("away")
                    if isinstance(hg, int) and isinstance(ag, int):
                        score = f"{hg}–{ag}"
            except Exception as e:
                print(f"Hiba fixture {fixture_id} ellenőrzésekor: {repr(e)}")
                result = "unknown"

        summary["total"] += 1
        if result in ("win", "lose", "pending", "unknown"):
            summary[result] += 1
        else:
            summary["unknown"] += 1

        summary["details"].append(
            {
                "fixture_id": fixture_id,
                "match": match_text,
                "tip": tip,
                "result": result,
                "status": status,
                "score": score,
            }
        )

    return summary


def _format_summary_line(summary: Dict[str, Any]) -> str:
    return (
        f"{summary['win']}/{summary['total']} találat "
        f"(nyertes: {summary['win']}✅, bukó: {summary['lose']}❌, "
        f"függő: {summary['pending']}⏳, ismeretlen: {summary['unknown']}⁉)"
    )


def build_daily_report_text(
    date_str: str,
    public_summary: Dict[str, Any],
    vip_summary: Dict[str, Any],
) -> str:
    """
    Rövid napi mérleg (összesítő) – kompatibilis a régi botoddal.
    """
    try:
        dt = datetime.date.fromisoformat(date_str)
        date_disp = dt.strftime("%Y.%m.%d.")
    except Exception:
        date_disp = date_str

    txt = (
        f"📊 Napi mérleg – SZELVÉNYKIRÁLY\n"
        f"({date_disp})\n\n"
        f"FREE: { _format_summary_line(public_summary) }\n"
        f"VIP:  { _format_summary_line(vip_summary) }\n\n"
        "Emlékeztető: fegyelmezett tét (1–3% bankroll) és hosszú távú gondolkodás. 💰"
    )
    return txt


def build_detailed_daily_report_text(
    title: str,
    date_str: str,
    summary: Dict[str, Any],
) -> str:
    """
    Részletes mérleg (a te példádhoz hasonló: listázza a meccseket + score).
    """
    try:
        dt = datetime.date.fromisoformat(date_str)
        date_disp = dt.strftime("%Y.%m.%d.")
    except Exception:
        date_disp = date_str

    decided = int(summary.get("win", 0)) + int(summary.get("lose", 0))
    hitrate = (summary.get("win", 0) / decided * 100.0) if decided > 0 else 0.0

    lines: List[str] = []
    lines.append(f"📊 {title}")
    lines.append(f"Dátum: {date_disp}\n")
    lines.append("Összefoglaló:")
    lines.append(f"✅ Nyertes tippek: {summary.get('win', 0)}")
    lines.append(f"❌ Vesztes tippek: {summary.get('lose', 0)}")
    lines.append(f"⏳ Függő / nem értékelt: {summary.get('pending', 0)}")
    lines.append(f"🎯 Találati arány (csak eldöntött tippek): {hitrate:.1f}%\n")

    details = summary.get("details") or []
    for i, d in enumerate(details, start=1):
        match = d.get("match") or "Ismeretlen meccs"
        tip = d.get("tip") or ""
        res = d.get("result") or "unknown"
        score = d.get("score") or ""
        status = d.get("status") or ""

        if res == "win":
            res_txt = f"✅ Nyert ({score})" if score else "✅ Nyert"
        elif res == "lose":
            res_txt = f"❌ Bukó ({score})" if score else "❌ Bukó"
        elif res == "pending":
            res_txt = f"⏳ Függő ({status}) {score}".strip()
        else:
            res_txt = "⁉ Nem értékelhető"

        lines.append(f"{i}. {match}\nTipp: {tip}\nEredmény: {res_txt}\n")

    return "\n".join(lines).strip()


def build_weekly_report_text(
    start_date_str: str,
    end_date_str: str,
    public_summaries: List[Dict[str, Any]],
    vip_summaries: List[Dict[str, Any]],
) -> str:
    def agg(summaries: List[Dict[str, Any]]) -> Dict[str, int]:
        agg_res = {"total": 0, "win": 0, "lose": 0, "pending": 0, "unknown": 0}
        for s in summaries:
            for k in agg_res.keys():
                agg_res[k] += int(s.get(k, 0))
        return agg_res

    try:
        start_disp = datetime.date.fromisoformat(start_date_str).strftime("%Y.%m.%d.")
    except Exception:
        start_disp = start_date_str

    try:
        end_disp = datetime.date.fromisoformat(end_date_str).strftime("%Y.%m.%d.")
    except Exception:
        end_disp = end_date_str

    pub_agg = agg(public_summaries)
    vip_agg = agg(vip_summaries)

    txt = (
        f"📊 Heti mérleg – SZELVÉNYKIRÁLY\n"
        f"({start_disp} – {end_disp})\n\n"
        f"FREE: { _format_summary_line(pub_agg) }\n"
        f"VIP:  { _format_summary_line(vip_agg) }\n\n"
        "Legfontosabb: hosszú táv, bankroll-védelem. 👑"
    )
    return txt
