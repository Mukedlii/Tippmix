import os
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import requests

from bot.results import evaluate_bets, build_daily_report_text

DATA_DIR = Path(__file__).resolve().parent / "data"


def send_telegram_message(token: str, chat_id: str, text: str, label: str) -> Tuple[bool, str]:
    """
    Ugyanaz a Telegram küldő, mint a main.py-ban, csak itt a recaphez használjuk.
    """
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


def _load_bets_from_json(filename: str):
    """
    Beolvassa a public_bets.json / vip_bets.json fájlokat.
    Visszaad: (date_str, bets_list)
    """
    path = DATA_DIR / filename
    if not path.exists():
        print(f"Figyelem: {filename} nem található ({path}).")
        return None, []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        date_str = data.get("date")
        bets = data.get("bets", [])
        return date_str, bets
    except Exception as e:
        print(f"Hiba a {filename} beolvasásakor:", repr(e))
        return None, []


def main() -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    # Döntsd el, hova menjen a napi mérleg – pl. VIP csatornába:
    recap_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID") or os.getenv("TELEGRAM_PUBLIC_CHAT_ID")

    print("\n=== NAPI MÉRLEG FUTÁS – TELEGRAM BEÁLLÍTÁSOK ===")
    print("TELEGRAM_BOT_TOKEN be van állítva:", bool(telegram_token))
    print("RECAP_CHAT_ID =", repr(recap_chat_id))

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN, kilépek.")
        return
    if not recap_chat_id:
        print("NINCS TELEGRAM_VIP_CHAT_ID vagy TELEGRAM_PUBLIC_CHAT_ID, kilépek.")
        return

    # 1) Public + VIP tippek beolvasása
    date_public, public_bets = _load_bets_from_json("public_bets.json")
    date_vip, vip_bets = _load_bets_from_json("vip_bets.json")

    date_str = date_public or date_vip
    if not date_str:
        print("Nem található dátum egyik JSON-ban sem – valószínűleg még nem futott a main.py.")
        return

    # 2) Kiértékelés (win/lose/pending/unknown)
    public_summary = evaluate_bets(public_bets)
    vip_summary = evaluate_bets(vip_bets)

    # 3) Napi mérleg szöveg generálása
    recap_text = build_daily_report_text(date_str, public_summary, vip_summary)

    # 4) Üzenet küldése Telegramra
    ok, err = send_telegram_message(
        token=telegram_token,
        chat_id=recap_chat_id,
        text=recap_text,
        label="DAILY_RECAP",
    )

    if not ok:
        print("Hiba a napi mérleg üzenet küldésekor:", err)
    else:
        print("Napi mérleg üzenet elküldve.")


if __name__ == "__main__":
    main()
