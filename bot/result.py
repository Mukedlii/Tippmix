import os
import datetime
from typing import Any, Dict, List

import requests

API_FOOTBALL_KEY = os.getenv("SPORTS_API_KEY")  # nálad amire be van állítva


def _get_fixture_result(fixture_id: int) -> Dict[str, Any]:
    """
    Lekéri egy meccs (fixture) végső eredményét az API-FOOTBALL-ból.
    """
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"id": fixture_id}
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("response"):
        return {}
    return data["response"][0]


def _settle_tip(tip: str, fixture: Dict[str, Any]) -> str:
    """
    Egyszerű kiértékelés pár alap piacra:
      - Hazai győzelem
      - Vendég győzelem
      - Over 2.5 gól
      - Over 1.5 gól
      - Under 2.5 gól
    Ha nem tudjuk értelmezni, 'unknown'.
    """
    if not fixture:
        return "unknown"

    goals = fixture.get("goals") or {}
    home_goals = goals.get("home")
    away_goals = goals.get("away")

    status = fixture.get("fixture", {}).get("status", {}).get("short")
    # Ha még nincs vége:
    if status not in ("FT", "AET", "PEN"):
        return "pending"

    if home_goals is None or away_goals is None:
        return "unknown"

    total_goals = home_goals + away_goals
    t = (tip or "").lower()

    # Egyszerű szöveg alapú matching
    if "hazai győzelem" in t:
        return "win" if home_goals > away_goals else "lose"
    if "vendég győzelem" in t:
        return "win" if away_goals > home_goals else "lose"
    if "over 2.5" in t:
        return "win" if total_goals > 2.5 else "lose"
    if "over 1.5" in t:
        return "win" if total_goals > 1.5 else "lose"
    if "under 2.5" in t:
        return "win" if total_goals < 2.5 else "lose"

    # Ha nem ismert típus
    return "unknown"


def evaluate_bets(bets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Végigmegy a tippeken, visszaad egy összesítést:
      - total
      - win
      - lose
      - pending
      - unknown
      - details: list of {match, tip, result}
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
        fixture_id = bet.get("fixture_id")
        tip = bet.get("tip")
        if not fixture_id:
            result = "unknown"
            fixture_data = {}
        else:
            try:
                fixture_data = _get_fixture_result(int(fixture_id))
                result = _settle_tip(tip, fixture_data)
            except Exception as e:
                print(f"Hiba fixture {fixture_id} ellenőrzésekor: {repr(e)}")
                result = "unknown"
                fixture_data = {}

        summary["total"] += 1
        if result in summary:
            summary[result] += 1
        else:
            summary["unknown"] += 1

        summary["details"].append(
            {
                "match": bet.get("match"),
                "tip": tip,
                "result": result,
            }
        )

    return summary


def _format_summary_line(summary: Dict[str, Any]) -> str:
    """
    FREE/VIP összegzés sor formázása.
    """
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
    Összerak egy Telegramra küldhető napi mérleg szöveget.
    date_str: pl. "2025-12-07"
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
        "Emlékeztető: ez nem sprint, hanem maraton. Lesznek jó napok, rossz napok, "
        "ezért fontos a fegyelmezett tét (1–3% bankroll) és a hosszú távú gondolkodás. 💰"
    )
    return txt


def build_weekly_report_text(
    start_date_str: str,
    end_date_str: str,
    public_summaries: List[Dict[str, Any]],
    vip_summaries: List[Dict[str, Any]],
) -> str:
    """
    Heti mérleg szöveg generálása.
    public_summaries / vip_summaries: több nap summary-ja összegyűjtve.
    """
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
        "Legfontosabb: a sportfogadás mindig kockázatos, ezért a cél nem az, hogy minden nap nyerjünk, "
        "hanem hogy hosszú távon, bankrollt védve játszunk. 👑"
    )
    return txt
