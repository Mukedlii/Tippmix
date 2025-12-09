import os
import json
import datetime
from typing import Any, Dict, Tuple

import requests

from bot.matches import fetch_matches_for_today
from bot.openai_logic import generate_tips


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


def main() -> None:
    today = datetime.date.today()
    print(f"Meccsek lekérése erre a napra: {today.isoformat()}")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    # Ha nincs PUBLIC_CHAT_ID setelve, fallback a megadott csatorna ID-re:
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

    # ⬇️ NINCS több early return: akkor is továbbmegyünk, ha matches üres.
    # Ilyenkor a generate_tips() saját fallback szöveget fog gyártani.

    # 2) Tipp generálás (OpenAI + fallback)
    tips_data = generate_tips(matches)

    public_text = tips_data.get("telegram_public_text") or "Hiba a FREE tippek generálásánál."
    vip_text = tips_data.get("telegram_vip_text") or "Hiba a VIP tippek generálásánál."

    # NAPI TIPPEK MENTÉSE JSON-BA – recap-hez
    public_bets = tips_data.get("public_bets", [])
    vip_bets = tips_data.get("vip_bets", [])

    try:
        with open("public_bets.json", "w", encoding="utf-8") as f:
            json.dump(public_bets, f, ensure_ascii=False, indent=2)
        with open("vip_bets.json", "w", encoding="utf-8") as f:
            json.dump(vip_bets, f, ensure_ascii=False, indent=2)
        print("Napi tippek elmentve: public_bets.json, vip_bets.json")
    except Exception as e:
        print("Nem sikerült a tippeket JSON-ba menteni:", repr(e))

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
