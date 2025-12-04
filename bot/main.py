import os
import datetime
from typing import Any, Dict

import requests

from bot.matches import fetch_matches_for_today
from bot.openai_logic import generate_tips


def send_telegram_message(token: str, chat_id: str, text: str, label: str) -> None:
    """
    Egyszerű Telegram küldés + részletes log a GitHub Actions-ben.
    label: 'PUBLIC' vagy 'VIP', csak a log kedvéért.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",            # ha később HTML-t használsz
        "disable_web_page_preview": True,
    }

    print(f"\n[{label}] Telegram sendMessage hívás indul...")
    print(f"[{label}] chat_id = {chat_id!r}")
    resp = requests.post(url, json=payload, timeout=20)
    print(f"[{label}] HTTP status: {resp.status_code}")
    print(f"[{label}] Válasz törzs: {resp.text}")

    try:
        resp.raise_for_status()
        print(f"[{label}] Üzenet sikeresen elküldve.")
    except Exception as e:
        print(f"[{label}] HIBA az üzenet küldésekor: {repr(e)}")


def main() -> None:
    today = datetime.date.today()
    print(f"Meccsek lekérése erre a napra: {today.isoformat()}")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

    # PUBLIC chat ID – vagy environmentből, vagy FIXEN a te csatornád:
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID") or "-1003307981597"
    # VIP chat ID továbbra is env-ből:
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")

    print("\n=== TELEGRAM BEÁLLÍTÁSOK ELLENŐRZÉSE ===")
    print("TELEGRAM_BOT_TOKEN be van állítva:", bool(telegram_token))
    print("PUBLIC_CHAT_ID (használt) =", repr(public_chat_id))
    print("VIP_CHAT_ID    =", repr(vip_chat_id))

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN, kilépek.")
        return

    # 1) Meccsek lekérése (foci + kosár)
    matches = fetch_matches_for_today()
    print(f"Talált meccsek száma: {len(matches)}")

    if not matches:
        print("Nincsenek meccsek mára, nem küldök tippet.")
        return

    # 2) Tipp generálás OpenAI-val / fallback-kel
    tips_data = generate_tips(matches)
    public_text = tips_data.get("telegram_public_text") or "Hiba a FREE tippek generálásánál."
    vip_text = tips_data.get("telegram_vip_text") or "Hiba a VIP tippek generálásánál."

    # 3) Üzenet küldés a nyilvános csatornára
    if public_chat_id:
        send_telegram_message(
            token=telegram_token,
            chat_id=public_chat_id,
            text=public_text,
            label="PUBLIC",
        )
    else:
        print("PUBLIC_CHAT_ID nincs beállítva, nem küldök FREE üzenetet.")

    # 4) Üzenet küldés a VIP csatornára
    if vip_chat_id:
        send_telegram_message(
            token=telegram_token,
            chat_id=vip_chat_id,
            text=vip_text,
            label="VIP",
        )
    else:
        print("VIP_CHAT_ID nincs beállítva, nem küldök VIP üzenetet.")


if __name__ == "__main__":
    main()
