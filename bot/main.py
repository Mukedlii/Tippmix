import os
import json
import datetime
from typing import Any, Dict, Tuple, List, Optional

import requests

from bot.matches import fetch_matches_for_today
from bot.openai_logic import generate_tips


def _split_telegram(text: str, max_len: int = 3900) -> List[str]:
    text = text or ""
    if len(text) <= max_len:
        return [text]
    parts: List[str] = []
    cur = ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 <= max_len:
            cur = (cur + "\n\n" + block).strip()
        else:
            if cur:
                parts.append(cur)
            cur = block
    if cur:
        parts.append(cur)
    return parts


def send_telegram_message(token: str, chat_id: str, text: str, label: str) -> Tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    parts = _split_telegram(text)
    print(f"\n[{label}] Telegram küldés indul... üzenet részek: {len(parts)}")

    for idx, part in enumerate(parts, start=1):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        print(f"[{label}] Part {idx}/{len(parts)} sendMessage...")
        try:
            resp = requests.post(url, json=payload, timeout=25)
        except Exception as e:
            err = f"Requests hiba: {repr(e)}"
            print(f"[{label}] {err}")
            return False, err

        print(f"[{label}] HTTP status: {resp.status_code}")
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text}"

        try:
            data = resp.json()
        except Exception as e:
            return False, f"JSON parse hiba: {repr(e)}"

        if not data.get("ok"):
            return False, f"Telegram API error: {data}"

    print(f"[{label}] Üzenet(ek) sikeresen elküldve.")
    return True, ""


def _extract_kickoff_hour(match: Dict[str, Any]) -> Optional[int]:
    dt = match.get("kickoff_local") or match.get("kickoff") or match.get("datetime") or match.get("date")
    if dt is None:
        return None
    if isinstance(dt, datetime.datetime):
        return dt.hour
    if isinstance(dt, str):
        s = dt.strip()
        try:
            parsed = datetime.datetime.fromisoformat(s)
            return parsed.hour
        except Exception:
            pass
        try:
            return int(s.split("T")[1][:2])
        except Exception:
            return None
    return None


def _filter_matches_for_slot(matches: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    """
    Biztonsági slot-szűrés, DE:
    - ha túl kevés meccs maradna, visszaadjuk az eredeti listát
    (mert tipp mindig kell)
    """
    slot = (slot or "DAY").upper()
    filtered: List[Dict[str, Any]] = []

    for m in matches:
        h = _extract_kickoff_hour(m)
        if h is None:
            filtered.append(m)
            continue

        if slot == "DAY":
            if 9 <= h < 16:
                filtered.append(m)
        else:
            if 16 <= h <= 23:
                filtered.append(m)

    # Minimumok (fizetős szolgáltatás -> mindig legyen elég meccs)
    min_vip = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
    min_free = int(os.getenv("TIPPMIX_MIN_FREE", "3"))
    min_need = min_vip + min_free  # pool minimálisan legyen ekkora

    if len(filtered) < min_need:
        print(f"[DEBUG] Slot szűrés után kevés meccs maradt ({len(filtered)} < {min_need}). Visszaadom az összes meccset.")
        return matches

    print(f"[DEBUG] Szűrt meccsszám slot={slot}: {len(filtered)} (eredeti: {len(matches)})")
    return filtered


def main() -> None:
    today = datetime.date.today()
    print(f"Meccsek lekérése erre a napra: {today.isoformat()}")

    slot = (os.getenv("TIPPMIX_SLOT") or "DAY").upper()
    print(f"Aktuális idősáv (TIPPMIX_SLOT): {slot}")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")

    print("\n=== TELEGRAM BEÁLLÍTÁSOK ===")
    print("TELEGRAM_BOT_TOKEN be van állítva:", bool(telegram_token))
    print("PUBLIC_CHAT_ID (használt) =", repr(public_chat_id))
    print("VIP_CHAT_ID    =", repr(vip_chat_id))

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN, kilépek.")
        return

    if not public_chat_id:
        print("[WARN] TELEGRAM_PUBLIC_CHAT_ID nincs beállítva! FREE üzenet nem fog kimenni.")
    if not vip_chat_id:
        print("[WARN] TELEGRAM_VIP_CHAT_ID nincs beállítva! VIP üzenet nem fog kimenni.")

    # 1) meccsek lekérése (matches.py már bővíti napokra, ha kell)
    try:
        matches = fetch_matches_for_today(slot=slot)
        print(f"Talált meccsek száma (összes): {len(matches)}")
    except Exception as e:
        err = f"⚠️ SPORT API HIBA ⚠️\n\nNem tudtam meccseket lekérni.\n\nTechnikai info:\n{repr(e)}"
        print("Meccslekérés közben hiba:", repr(e))
        if public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, err, f"PUBLIC_API_ERROR_{slot}")
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, err, f"VIP_API_ERROR_{slot}")
        return

    # 1/b) Biztonsági slot szűrés (de nem engedjük, hogy túl kevés legyen)
    slot_matches = _filter_matches_for_slot(matches, slot)
    print(f"Idősávra szűrt meccsek száma: {len(slot_matches)}")

    # 2) tippek
    tips_data = generate_tips(slot_matches)

    public_text = tips_data.get("telegram_public_text") or "⚠️ Hiba a FREE tippek generálásánál."
    vip_text = tips_data.get("telegram_vip_text") or "⚠️ Hiba a VIP tippek generálásánál."

    # 3) mentés recap-hez
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
        print("Nem sikerült JSON-ba menteni:", repr(e))

    # 4) küldés
    if public_chat_id:
        send_telegram_message(telegram_token, public_chat_id, public_text, f"PUBLIC_{slot}")
    if vip_chat_id:
        send_telegram_message(telegram_token, vip_chat_id, vip_text, f"VIP_{slot}")


if __name__ == "__main__":
    main()
