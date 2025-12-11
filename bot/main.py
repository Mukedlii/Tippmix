import os
import json
import datetime
from typing import Any, Dict, Tuple, List, Optional

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


def _extract_kickoff_hour(match: Dict[str, Any]) -> Optional[int]:
    """
    Megpróbáljuk kivenni az órát a meccs kezdési idejéből (helyi idő szerint).
    Először kickoff_local, kickoff, datetime, date mezőkből próbál.
    Elfogad:
      - datetime objektumot
      - ISO stringet (2025-12-10T11:00:00)
      - sima 'HH:MM' stringet
    Ha nem tudjuk, None-t ad vissza.
    """
    dt = (
        match.get("kickoff_local")
        or match.get("kickoff")
        or match.get("datetime")
        or match.get("date")
    )

    if dt is None:
        return None

    if isinstance(dt, datetime.datetime):
        return dt.hour

    if isinstance(dt, str):
        s = dt.strip()
        # Próbáljuk ISO datetime-ként
        try:
            parsed = datetime.datetime.fromisoformat(s)
            return parsed.hour
        except Exception:
            pass

        # Próbáljuk HH:MM formaként
        parts = s.split(":")
        if len(parts) >= 1:
            try:
                return int(parts[0])
            except Exception:
                return None

    return None


def _filter_matches_for_slot(matches: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    """
    Két idősáv:
      - DAY:   9:00–16:00 (9 <= óra < 16)
      - EVENING: 16:00–23:00 (16 <= óra <= 23)
    Ha nem tudjuk kivenni az órát, bent hagyjuk (hogy inkább legyen tipp).
    Ha a szűrés után üres, visszaadjuk az eredeti listát.
    """
    slot = (slot or "DAY").upper()
    filtered: List[Dict[str, Any]] = []

    for m in matches:
        h = _extract_kickoff_hour(m)
        if h is None:
            # Nem tudtuk eldönteni, akkor hagyjuk bent
            filtered.append(m)
            continue

        if slot == "DAY":
            if 9 <= h < 16:
                filtered.append(m)
        else:  # EVENING
            if 16 <= h <= 23:
                filtered.append(m)

    if not filtered:
        print(f"[DEBUG] Az idősáv szűrés üres eredményt adott (slot={slot}), visszaadom az összes meccset.")
        return matches

    print(f"[DEBUG] Szűrt meccsszám slot={slot}: {len(filtered)} (eredeti: {len(matches)})")
    return filtered


def main() -> None:
    today = datetime.date.today()
    print(f"Meccsek lekérése erre a napra: {today.isoformat()}")

    # SLOT: DAY vagy EVENING (GitHub Actions env-ből állítjuk)
    slot = os.getenv("TIPPMIX_SLOT", "DAY").upper()
    print(f"Aktuális idősáv (TIPPMIX_SLOT): {slot}")

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

    # 1) Meccsek lekérése sport API-ból – most try/except-tel
    try:
        matches = fetch_matches_for_today()
        print(f"Talált meccsek száma (összes): {len(matches)}")
    except Exception as e:
        err_msg = (
            "⚠️ SPORT API HIBA ⚠️\n\n"
            "Ma nem tudtam meccseket lekérni az API-FOOTBALL rendszertől.\n"
            "Valószínűleg a sport API fiók fel van függesztve vagy limitet ért el.\n\n"
            f"Technikai info:\n{repr(e)}"
        )
        print("Meccslekérés közben hiba történt:", repr(e))

        # Küldjük ki FREE + VIP csatornára, hogy tudjanak róla
        if public_chat_id:
            send_telegram_message(
                token=telegram_token,
                chat_id=public_chat_id,
                text=err_msg,
                label=f"PUBLIC_API_ERROR_{slot}",
            )
        if vip_chat_id:
            send_telegram_message(
                token=telegram_token,
                chat_id=vip_chat_id,
                text=err_msg,
                label=f"VIP_API_ERROR_{slot}",
            )
        return

    if not matches:
        print("Nincsenek meccsek mára, nem küldök tippet.")
        return

    # 1/b) Csak az adott idősáv (DAY / EVENING) meccsei
    slot_matches = _filter_matches_for_slot(matches, slot)
    print(f"Idősávra szűrt meccsek száma: {len(slot_matches)}")

    # 2) Tipp generálás (OpenAI + fallback) az idősávra
    tips_data = generate_tips(slot_matches)

    public_text = tips_data.get("telegram_public_text") or "Hiba a FREE tippek generálásánál."
    vip_text = tips_data.get("telegram_vip_text") or "Hiba a VIP tippek generálásánál."

    # NAPI TIPPEK MENTÉSE JSON-BA – recap-hez
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

    # 3) FREE / PUBLIC üzenet küldése
    public_ok = False
    public_err = ""

    if public_chat_id:
        public_ok, public_err = send_telegram_message(
            token=telegram_token,
            chat_id=public_chat_id,
            text=public_text,
            label=f"PUBLIC_{slot}",
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
            label=f"VIP_{slot}",
        )
    else:
        print("VIP_CHAT_ID nincs beállítva, nem küldök VIP üzenetet.")


if __name__ == "__main__":
    main()
