# bot/daily_recap_main.py
import os
import json
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from bot.tips_logger import read_tips


# -----------------------------
# Telegram
# -----------------------------
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

    print(f"\n[{label}] Telegram recap küldés indul... üzenet részek: {len(parts)}")

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

    print(f"[{label}] Recap üzenet(ek) sikeresen elküldve.")
    return True, ""


# -----------------------------
# API-Football (api-sports) result fetch
# -----------------------------
def _api_football_headers() -> Dict[str, str]:
    key = (os.getenv("SPORTS_API_KEY") or "").strip()
    # api-sports v3 header
    return {"x-apisports-key": key}


def _fetch_fixture(fixture_id: int) -> Optional[Dict[str, Any]]:
    key = (os.getenv("SPORTS_API_KEY") or "").strip()
    if not key:
        return None

    url = "https://v3.football.api-sports.io/fixtures"
    try:
        resp = requests.get(url, headers=_api_football_headers(), params={"id": str(fixture_id)}, timeout=25)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    arr = (data.get("response") or [])
    if not arr:
        return None
    return arr[0]


def _status_is_finished(short: str) -> bool:
    s = (short or "").upper()
    return s in {"FT", "AET", "PEN"}


def _result_1x2(goals_home: Optional[int], goals_away: Optional[int]) -> Optional[str]:
    if goals_home is None or goals_away is None:
        return None
    if goals_home > goals_away:
        return "1"
    if goals_home < goals_away:
        return "2"
    return "X"


def _pick_to_1x2(pick_hu: str) -> Optional[str]:
    p = (pick_hu or "").strip()
    if p == "Hazai győzelem":
        return "1"
    if p == "Vendég győzelem":
        return "2"
    if p == "Döntetlen":
        return "X"
    return None


def _format_score(fx: Dict[str, Any]) -> str:
    goals = (fx.get("goals") or {})
    gh = goals.get("home")
    ga = goals.get("away")
    if gh is None or ga is None:
        return "–"
    return f"{gh}–{ga}"


# -----------------------------
# Recap builder
# -----------------------------
def _evaluate_bets(bets: List[Dict[str, Any]]) -> Tuple[int, int, int, List[str]]:
    """
    returns: (win, loss, pending, lines)
    """
    win = loss = pending = 0
    lines: List[str] = []

    for i, b in enumerate(bets, 1):
        fid = b.get("fixture_id")
        pick = b.get("tip") or b.get("selection") or b.get("pick") or ""
        match_label = b.get("match") or b.get("label") or f"fixture_id={fid}"

        try:
            fid_int = int(fid)
        except Exception:
            pending += 1
            lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ❓ hibás fixture_id")
            continue

        fx = _fetch_fixture(fid_int)
        if not fx:
            pending += 1
            lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ❓ nincs adat (API)")
            continue

        st = ((fx.get("fixture") or {}).get("status") or {})
        short = st.get("short") or ""
        score = _format_score(fx)

        if not _status_is_finished(short):
            pending += 1
            lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ⏳ függő ({score}, status={short})")
            continue

        goals = (fx.get("goals") or {})
        gh = goals.get("home")
        ga = goals.get("away")

        res = _result_1x2(gh, ga)
        sel = _pick_to_1x2(pick)

        if not res or not sel:
            pending += 1
            lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ❓ nem értelmezhető ({score})")
            continue

        if res == sel:
            win += 1
            lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ✅ Nyert ({score})")
        else:
            loss += 1
            lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ❌ Vesztett ({score})")

    return win, loss, pending, lines


def main() -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN, kilépek.")
        return

    slot = (os.getenv("TIPPMIX_SLOT") or "EVENING").upper()
    # recap-nél az EVENING/DAY mindkettő jöhet
    if slot not in {"DAY", "EVENING"}:
        slot = "EVENING"

    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    tips = read_tips(slot=slot, base_dir=".")
    vip_bets = tips.get("vip_bets") or []
    public_bets = tips.get("public_bets") or []

    # ha nincs mentett tipp, ne bukjon a workflow
    if not vip_bets and not public_bets:
        msg = (
            f"📊 SZELVÉNYKIRÁLY – NAPI MÉRLEG ({slot_text})\n"
            f"Dátum: {today}\n\n"
            "⚠️ Nincs mentett tipp fájl a recap-hez.\n"
            "Ellenőrizd: vip_bets_*.json / public_bets_*.json"
        )
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, msg, f"VIP_RECAP_{slot}")
        if public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, msg, f"PUBLIC_RECAP_{slot}")
        return

    vip_w, vip_l, vip_p, vip_lines = _evaluate_bets(vip_bets)
    pub_w, pub_l, pub_p, pub_lines = _evaluate_bets(public_bets)

    def hitrate(w: int, l: int) -> float:
        d = w + l
        return (100.0 * w / d) if d > 0 else 0.0

    vip_msg = (
        f"📊 SZELVÉNYKIRÁLY – NAPI MÉRLEG (VIP ({slot_text}))\n"
        f"Dátum: {today}\n\n"
        f"Összefoglaló:\n"
        f"✅ Nyertes tippek: {vip_w}\n"
        f"❌ Vesztes tippek: {vip_l}\n"
        f"⏳ Függő / nem értékelt: {vip_p}\n"
        f"🎯 Találati arány (csak eldöntött tippek): {hitrate(vip_w, vip_l):.1f}%\n\n"
        + "\n\n".join(vip_lines[:25])
    )

    pub_msg = (
        f"📊 SZELVÉNYKIRÁLY – NAPI MÉRLEG (FREE ({slot_text}))\n"
        f"Dátum: {today}\n\n"
        f"Összefoglaló:\n"
        f"✅ Nyertes tippek: {pub_w}\n"
        f"❌ Vesztes tippek: {pub_l}\n"
        f"⏳ Függő / nem értékelt: {pub_p}\n"
        f"🎯 Találati arány (csak eldöntött tippek): {hitrate(pub_w, pub_l):.1f}%\n\n"
        + "\n\n".join(pub_lines[:25])
    )

    if vip_chat_id:
        send_telegram_message(telegram_token, vip_chat_id, vip_msg, f"VIP_RECAP_{slot}")
    if public_chat_id:
        send_telegram_message(telegram_token, public_chat_id, pub_msg, f"PUBLIC_RECAP_{slot}")


if __name__ == "__main__":
    main()

