import os
import datetime
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import requests

from bot.matches import fetch_matches_for_today
from bot.openai_logic import generate_tips

# Itt fogjuk tárolni a napi tippeket (csak a futás idejére)
DATA_DIR = Path(__file__).resolve().parent / "data"


def send_telegram_message(token: str, chat_id: str, text: str, label: str) -> Tuple[bool, str]:
    """
    Egyszerű Telegram küldés + részletes log.
    Visszaadja: (sikeres-e, hiba_szöveg_vagy_üres).
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


def _save_bets_for_recap(date_str: str, public_bets, vip_bets) -> None:
    """
    Elmenti a napi public + VIP tippeket JSON fájlokba,
    hogy a daily_recap_main.py később fel tudja dolgozni.
    """
    try:
        DATA_DIR.mkdir(exist_ok=True)

        public_payload = {
            "date": date_str,
            "bets": public_bets or [],
        }
        vip_payload = {
            "date": date_str,
            "bets": vip_bets or [],
        }

        with open(DATA_DIR / "public_bets.json", "w", encoding="utf-8") as f:
            json.dump(public_payload, f, ensure_ascii=False, indent=2)

        with open(DATA_DIR / "vip_bets.json", "w", encoding="utf-8") as f:
            json.dump(vip_payload, f, ensure_ascii=False, indent=2)

        print("Napi tippek elmentve:")
        print(f"  - {DATA_DIR / 'public_bets.json'}")
        print(f"  - {DATA_DIR / 'vip_bets.json'}")
    except Exception as e:
        print("Hiba a tippek mentésekor:", repr(e))


def main() -> None:
    today = datetime.date.today()
    print(f"Meccsek lekérése erre a napra: {today.isoformat()}")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID") or "-1003307981597"
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")

    print("\n=== TELEGRAM BEÁLLÍTÁSOK ELLENŐRZÉSE ===")
    print("TELEGRAM_BOT_TOKEN be van állítva:", bool(telegram_token))
    print("PUBLIC_CHAT_ID (használt) =", repr(public_chat_id))
    print("VIP_CHAT_ID    =", repr(vip_chat_id))

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN, kilépek.")
        return

    # 1) Meccsek lekérése
    matches = fetch_matches_for_today()
    print(f"Talált meccsek száma: {len(matches)}")

    if not matches:
        print("Nincsenek meccsek mára, nem küldök tippet.")
        return

    # 2) Tipp generálás (OpenAI + fallback)
    tips_data = generate_tips(matches)
    public_text = tips_data.get("telegram_public_text") or "Hiba a FREE tippek generálásánál."
    vip_text = tips_data.get("telegram_vip_text") or "Hiba a VIP tippek generálásánál."

    # <-- ÚJ: nyers tippek a mérleghez
    public_bets = tips_data.get("public_bets", [])
    vip_bets = tips_data.get("vip_bets", [])

    # Napi tippek elmentése JSON-ba
    _save_bets_for_recap(today.isoformat(), public_bets, vip_bets)

    # 3) FREE / PUBLIC üzenet küldése
    public_ok = False
    public_err = ""

    if public_chat_id:
        public_ok, public_err = send_telegram_message(
            token=telegram_token,
            chat_id=public_chat_id,
            text=public_text,
            label="PUBLIC",
        )
    else:
        public_err = "PUBLIC_CHAT_ID nincs beállítva."
        print(public_err)

    # 4) VIP üzenet – ha a FREE-nél hiba volt, technikai infót csatolunk
    if vip_chat_id:
        if not public_ok and public_err:
            vip_text_with_info = (
                vip_text
                + "\n\n⚠️ TECH INFO (FREE csatorna):\n"
                + public_err
            )
        else:
            vip_text_with_info = vip_text

        send_telegram_message(
            token=telegram_token,
            chat_id=vip_chat_id,
            text=vip_text_with_info,
            label="VIP",
        )
    else:
        print("VIP_CHAT_ID nincs beállítva, nem küldök VIP üzenetet.")


if __name__ == "__main__":
    main()
