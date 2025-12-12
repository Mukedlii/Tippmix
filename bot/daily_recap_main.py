import os
import json
import datetime
from typing import Any, Dict, List, Tuple

import requests

# --- TELEGRAM KÜLDŐ -------------------------------------------------


def send_telegram_message(token: str, chat_id: str, text: str, label: str) -> Tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    print(f"\n[{label}] Telegram sendMessage hívás indul...")
    print(f"[{label}] chat_id = {chat_id!r}")
    try:
        resp = requests.post(url, json=payload, timeout=20)
    except Exception as e:
        err = f"Requests hiba: {repr(e)}"
        print(f"[{label}] {err}")
        return False, err

    print(f"[{label}] HTTP status: {resp.status_code}")
    print(f"[{label}] Válasz törzs: {resp.text}")

    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text}"

    try:
        data = resp.json()
    except Exception as e:
        err = f"JSON parse hiba: {repr(e)}"
        print(f"[{label}] {err}")
        return False, err

    if not data.get("ok"):
        err = f"Telegram API error: {data}"
        print(f"[{label}] {err}")
        return False, err

    print(f"[{label}] Üzenet sikeresen elküldve.")
    return True, ""


# --- API-FOOTBALL / SPORTS API EREDMÉNY LEKÉRÉS ---------------------


SPORTS_API_KEY = os.getenv("SPORTS_API_KEY")


def fetch_fixture_result(fixture_id: int) -> Tuple[int | None, int | None, str]:
    """
    Visszaadja: (home_goals, away_goals, status_short)
    Ha hiba van, minden None / "ERR".
    """
    if not SPORTS_API_KEY:
        print("Nincs SPORTS_API_KEY beállítva, nem tudok eredményt lekérni.")
        return None, None, "ERR"

    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": SPORTS_API_KEY}
    params = {"id": fixture_id}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
    except Exception as e:
        print(f"Fixture {fixture_id} lekérési hiba:", repr(e))
        return None, None, "ERR"

    if resp.status_code != 200:
        print(f"Fixture {fixture_id} HTTP hiba:", resp.status_code, resp.text)
        return None, None, "ERR"

    try:
        data = resp.json()
    except Exception as e:
        print("JSON hiba fixture resultnál:", repr(e))
        return None, None, "ERR"

    if not data.get("response"):
        print(f"Fixture {fixture_id} üres response.")
        return None, None, "ERR"

    item = data["response"][0]
    goals = item.get("goals") or {}
    fixture = item.get("fixture") or {}
    status = (fixture.get("status") or {}).get("short") or "UNK"

    home_goals = goals.get("home")
    away_goals = goals.get("away")
    return home_goals, away_goals, status


# --- TIPP KIÉRTÉKELÉS -----------------------------------------------


def _evaluate_tip(tip: str, home_goals: int | None, away_goals: int | None, status: str) -> str:
    """
    Visszatér: 'win', 'lose' vagy 'pending'.
    """
    t = (tip or "").lower().strip()

    if home_goals is None or away_goals is None:
        return "pending"

    if status not in {"FT", "AET", "PEN"}:
        return "pending"

    total_goals = home_goals + away_goals

    # 1X2 alap
    if "hazai" in t and "győzelem" in t and "vagy" not in t:
        return "win" if home_goals > away_goals else "lose"

    if ("vendég" in t or "idegen" in t) and "győzelem" in t and "vagy" not in t:
        return "win" if away_goals > home_goals else "lose"

    if "döntetlen" in t and "vagy" not in t:
        return "win" if home_goals == away_goals else "lose"

    # dupla esély
    if "1x" in t or ("hazai" in t and "döntetlen" in t):
        return "win" if home_goals >= away_goals else "lose"

    if "x2" in t or ("vendég" in t and "döntetlen" in t):
        return "win" if away_goals >= home_goals else "lose"

    if "12" in t:
        return "win" if home_goals != away_goals else "lose"

    # Over / Under 2.5 gól
    if "over 2.5" in t or "2.5 gól felett" in t or "2,5 gól felett" in t:
        return "win" if total_goals > 2.5 else "lose"

    if "under 2.5" in t or "2.5 gól alatt" in t or "2,5 gól alatt" in t:
        return "win" if total_goals < 2.5 else "lose"

    # BTTS
    if "mindkét csapat szerez gólt" in t or "btts" in t:
        return "win" if home_goals > 0 and away_goals > 0 else "lose"

    return "pending"


def _load_bets(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        print(f"{path} nem létezik, nem tudok belőle olvasni.")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Hiba a {path} beolvasásánál:", repr(e))
        return []


def _build_recap_text(label: str, bets: List[Dict[str, Any]]) -> str:
    today = datetime.date.today().strftime("%Y.%m.%d.")
    lines: List[str] = []

    win = lose = pend = 0

    for idx, bet in enumerate(bets, start=1):
        match = bet.get("match") or "Ismeretlen meccs"
        tip = bet.get("tip") or "N/A"
        fixture_id = bet.get("fixture_id")

        if not fixture_id:
            status_emoji = "❓"
            result_text = "Nincs fixture_id, nem tudtam kiértékelni."
            pend += 1
        else:
            try:
                fixture_id_int = int(fixture_id)
            except Exception:
                fixture_id_int = None

            if fixture_id_int is None:
                status_emoji = "❓"
                result_text = "Érvénytelen fixture_id, nem tudtam kiértékelni."
                pend += 1
            else:
                home_goals, away_goals, status = fetch_fixture_result(fixture_id_int)

                if home_goals is None or away_goals is None:
                    status_emoji = "❓"
                    result_text = f"Nem elérhető eredmény (status={status})."
                    pend += 1
                else:
                    outcome = _evaluate_tip(tip, home_goals, away_goals, status)
                    score_str = f"{home_goals}–{away_goals}"

                    if outcome == "win":
                        status_emoji = "✅"
                        result_text = f"Nyert ({score_str})"
                        win += 1
                    elif outcome == "lose":
                        status_emoji = "❌"
                        result_text = f"Vesztett ({score_str})"
                        lose += 1
                    else:
                        status_emoji = "⏳"
                        result_text = f"Még nincs végeredmény vagy nem értelmezett piac ({score_str})"
                        pend += 1

        lines.append(
            f"{idx}. {match}\n"
            f"Tipp: {tip}\n"
            f"Eredmény: {status_emoji} {result_text}"
        )

    total_played = win + lose
    hit_rate = (win / total_played * 100) if total_played > 0 else 0.0

    header = (
        f"📊 SZELVÉNYKIRÁLY – NAPI MÉRLEG ({label})\n"
        f"Dátum: {today}\n\n"
    )

    summary = (
        "Összefoglaló:\n"
        f"✅ Nyertes tippek: {win}\n"
        f"❌ Vesztes tippek: {lose}\n"
        f"⏳ Függő / nem értékelt: {pend}\n"
        f"🎯 Találati arány (csak eldöntött tippek): {hit_rate:.1f}%\n\n"
    )

    body = "\n\n".join(lines) if lines else "Ma nem találtam kiértékelhető tippet ebben a kategóriában."

    return header + summary + body


# --- FŐFÜGGVÉNY -----------------------------------------------------


def main() -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")

    slot = (os.getenv("TIPPMIX_SLOT") or "DAY").upper()

    print("=== DAILY RECAP INDUL ===")
    print("TIPPMIX_SLOT:", slot)
    print("TELEGRAM_BOT_TOKEN be van állítva:", bool(telegram_token))

    if not telegram_token:
        print("Nincs TELEGRAM_BOT_TOKEN, kilépek.")
        return

    if slot == "DAY":
        public_path = "public_bets_day.json"
        vip_path = "vip_bets_day.json"
        label_suffix = " (délelőtt / nappal)"
    elif slot == "EVENING":
        public_path = "public_bets_evening.json"
        vip_path = "vip_bets_evening.json"
        label_suffix = " (este)"
    else:
        public_path = "public_bets.json"
        vip_path = "vip_bets.json"
        label_suffix = ""

    print(f"Bet JSON-ok: {public_path} {vip_path}")

    public_bets = _load_bets(public_path)
    vip_bets = _load_bets(vip_path)

    if not public_bets and not vip_bets:
        print("Nincs kiértékelhető tipp ebben az idősávban.")
        return

    # FREE recap
    if public_bets and public_chat_id:
        text_public = _build_recap_text("FREE" + label_suffix, public_bets)
        send_telegram_message(telegram_token, public_chat_id, text_public, "RECAP_PUBLIC")

    # VIP recap
    if vip_bets and vip_chat_id:
        text_vip = _build_recap_text("VIP" + label_suffix, vip_bets)
        send_telegram_message(telegram_token, vip_chat_id, text_vip, "RECAP_VIP")

    print("=== DAILY RECAP VÉGE ===")


if __name__ == "__main__":
    main()
