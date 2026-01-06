import os
import json
import datetime
from typing import Any, Dict, Tuple, List, Optional

import requests

from bot.matches import fetch_matches_for_today
from bot.openai_logic import generate_tips


def _chunk_text(text: str, max_len: int = 3800) -> List[str]:
    parts: List[str] = []
    s = text or ""
    while len(s) > max_len:
        cut = s.rfind("\n", 0, max_len)
        if cut < 500:
            cut = max_len
        parts.append(s[:cut])
        s = s[cut:].lstrip()
    if s:
        parts.append(s)
    return parts


def send_telegram_message(token: str, chat_id: str, text: str, label: str) -> Tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    if not chat_id:
        return False, "chat_id üres"

    parts = _chunk_text(text)
    print(f"\n[{label}] Telegram küldés indul... üzenet részek: {len(parts)}")

    last_err = ""
    for i, part in enumerate(parts, start=1):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        print(f"[{label}] Part {i}/{len(parts)} sendMessage...")
        try:
            resp = requests.post(url, json=payload, timeout=25)
        except Exception as e:
            last_err = f"Requests hiba: {repr(e)}"
            print(f"[{label}] {last_err}")
            return False, last_err

        print(f"[{label}] HTTP status: {resp.status_code}")
        if resp.status_code != 200:
            last_err = f"HTTP {resp.status_code}: {resp.text[:800]}"
            print(f"[{label}] {last_err}")
            return False, last_err

        try:
            data = resp.json()
        except Exception as e:
            last_err = f"JSON parse hiba: {repr(e)}"
            print(f"[{label}] {last_err}")
            return False, last_err

        if not data.get("ok"):
            last_err = f"Telegram API error: {str(data)[:800]}"
            print(f"[{label}] {last_err}")
            return False, last_err

    print(f"[{label}] Üzenet(ek) sikeresen elküldve.")
    return True, ""


def main() -> None:
    today = datetime.date.today()
    print(f"Meccsek lekérése erre a napra: {today.isoformat()}")

    slot = (os.getenv("TIPPMIX_SLOT") or "DAY").upper()
    print(f"Aktuális idősáv (TIPPMIX_SLOT): {slot}")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID") or ""
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID") or ""

    print("\n=== TELEGRAM BEÁLLÍTÁSOK ===")
    print("TELEGRAM_BOT_TOKEN be van állítva:", bool(telegram_token))
    print("PUBLIC_CHAT_ID (használt) =", repr(public_chat_id))
    print("VIP_CHAT_ID    =", repr(vip_chat_id))

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN, kilépek.")
        return

    # 1) Meccsek
    try:
        matches = fetch_matches_for_today(slot=slot)
        print(f"Talált meccsek száma (összes): {len(matches)}")
    except Exception as e:
        msg = (
            "⚠️ SPORT / MATCH API HIBA ⚠️\n\n"
            "Nem tudtam meccseket lekérni az API-kból.\n"
            f"Technikai info: {repr(e)}"
        )
        print(msg)

        if public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, msg, f"PUBLIC_API_ERROR_{slot}")
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, msg, f"VIP_API_ERROR_{slot}")
        return

    # 2) Ha 0 meccs: státusz üzenet (nincs hallucináció)
    if not matches:
        msg = (
            "⚠️ NINCS MECCS ADAT ⚠️\n\n"
            "Ma egyik API-ból sem jött vissza meccs (SportAPI / Football-Data / SportMonks).\n"
            "Ellenőrizd a kulcsokat, limitet, és hogy a provider elérhető-e."
        )
        if public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, msg, f"PUBLIC_NO_MATCHES_{slot}")
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, msg, f"VIP_NO_MATCHES_{slot}")
        return

    # 3) Tippek generálása
    tips_data = generate_tips(matches)
    public_text = tips_data.get("telegram_public_text") or "Hiba a FREE tippek generálásánál."
    vip_text = tips_data.get("telegram_vip_text") or "Hiba a VIP tippek generálásánál."

    # 4) JSON mentés recap-hez
    public_bets = tips_data.get("public_bets", [])
    vip_bets = tips_data.get("vip_bets", [])

    suffix = "day" if slot == "DAY" else "evening"
    public_json_path = f"public_bets_{suffix}.json"
    vip_json_path = f"vip_bets_{suffix}.json"

    try:
        with open(public_json_path, "w", encoding="utf-8") as f:
            json.dump(public_bets, f, ensure_ascii=False, indent=2)
        with open(vip_json_path, "w", encoding="utf-8") as f:
            json.dump(vip_bets, f, ensure_ascii=False, indent=2)
        print(f"Napi tippek elmentve: {public_json_path}, {vip_json_path}")
    except Exception as e:
        print("Nem sikerült a tippeket JSON-ba menteni:", repr(e))

    # 5) Küldés
    public_ok, public_err = (True, "")
    if public_chat_id:
        public_ok, public_err = send_telegram_message(telegram_token, public_chat_id, public_text, f"PUBLIC_{slot}")

    if vip_chat_id:
        if not public_ok and public_err:
            vip_text = vip_text + "\n\n⚠️ TECH INFO (FREE):\n" + public_err
        send_telegram_message(telegram_token, vip_chat_id, vip_text, f"VIP_{slot}")


if __name__ == "__main__":
    main()
