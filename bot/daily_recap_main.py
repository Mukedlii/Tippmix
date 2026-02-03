# bot/daily_recap_main.py
import os
import json
import datetime
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from bot.api_keys import get_optional_api_sports_key, get_optional_sportsdataio_key, resolve_sports_provider
from bot.tips_logger import read_tips
from bot.providers import sportsdataio
from bot.storage.sqlite_store import upsert_result


# -----------------------------
# Duplicate-send guard (GitHub Actions fallback retries)
# -----------------------------
_MARKER_PATH = os.path.join("data", "recap_sent.json")


def _load_marker() -> Dict[str, Any]:
    try:
        with open(_MARKER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_marker(marker: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_MARKER_PATH), exist_ok=True)
    with open(_MARKER_PATH, "w", encoding="utf-8") as f:
        json.dump(marker, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _should_skip_due_to_marker(slot: str, date_iso: str) -> bool:
    # allow manual override
    if (os.getenv("TIPPMIX_FORCE_RECAP") or "").strip() == "1":
        return False

    marker = _load_marker()
    sent = (marker.get(slot) or "").strip()
    return sent == date_iso


def _mark_sent(slot: str, date_iso: str) -> None:
    marker = _load_marker()
    marker[slot] = date_iso
    _save_marker(marker)


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
    # api-sports v3 header
    return {"x-apisports-key": get_optional_api_sports_key()}


def _detect_provider() -> Optional[str]:
    """Best-effort provider detection.

    IMPORTANT: Recap should not silently run without any provider key; otherwise every match becomes
    '❓ nincs adat (API)' which is misleading.
    """
    try:
        return resolve_sports_provider()
    except Exception:
        # fall back to old optional-key probing
        if get_optional_api_sports_key():
            return "api-sports"
        if get_optional_sportsdataio_key():
            return "sportsdataio"
        return None


def _fetch_fixture(fixture_id: int) -> Tuple[Optional[Dict[str, Any]], str]:
    """Fetch fixture + return a short diagnostic status string.

    Tries the configured provider first. If it returns NO_DATA and the other provider key is also
    present, we attempt a fallback provider. This fixes cases where tips were generated with one
    provider but recap runs with the other.
    """

    def _fetch_sportsdataio(fid: int) -> Tuple[Optional[Dict[str, Any]], str]:
        fx = sportsdataio.fetch_game_by_id(fid)
        return (fx, "OK") if fx else (None, "NO_DATA")

    def _fetch_apisports(fid: int) -> Tuple[Optional[Dict[str, Any]], str]:
        url = "https://v3.football.api-sports.io/fixtures"

        # small retry for transient API failures
        last_status = "NO_DATA"
        for attempt in range(2):
            try:
                resp = requests.get(url, headers=_api_football_headers(), params={"id": str(fid)}, timeout=25)
            except Exception:
                last_status = "REQUEST_ERROR"
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    return None, "BAD_JSON"

                arr = (data.get("response") or [])
                if not arr:
                    return None, "NO_DATA"
                return arr[0], "OK"

            # rate limit / temporary issues
            if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                last_status = f"HTTP_{resp.status_code}"
                try:
                    time.sleep(2)
                except Exception:
                    pass
                continue

            return None, f"HTTP_{resp.status_code}"

        return None, last_status

    provider = _detect_provider()
    if not provider:
        return None, "NO_PROVIDER_KEY"

    has_api_sports = bool(get_optional_api_sports_key())
    has_sdio = bool(get_optional_sportsdataio_key())

    # primary
    if provider == "sportsdataio":
        fx, st = _fetch_sportsdataio(fixture_id)
        if fx or st != "NO_DATA" or not has_api_sports:
            return fx, st
        # fallback
        fx2, st2 = _fetch_apisports(fixture_id)
        return fx2, ("FALLBACK_API_SPORTS" if fx2 else f"NO_DATA_BOTH({st2})")

    fx, st = _fetch_apisports(fixture_id)
    if fx or st != "NO_DATA" or not has_sdio:
        return fx, st
    fx2, st2 = _fetch_sportsdataio(fixture_id)
    return fx2, ("FALLBACK_SPORTSDATAIO" if fx2 else f"NO_DATA_BOTH({st2})")


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
    if _detect_provider() == "sportsdataio":
        gh = fx.get("HomeTeamScore")
        ga = fx.get("AwayTeamScore")
        if gh is None or ga is None:
            return "–"
        return f"{gh}–{ga}"

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
    """returns: (win, loss, pending, lines)"""
    win = loss = pending = 0
    lines: List[str] = []

    last_call_ts = 0.0

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

        # Simple pacing to reduce 429 risk on API-Sports.
        # (SportsDataIO tends to be less strict, but pacing is harmless.)
        now = time.time()
        if now - last_call_ts < 0.6:
            try:
                time.sleep(0.6 - (now - last_call_ts))
            except Exception:
                pass
        last_call_ts = time.time()

        fx, fx_status = _fetch_fixture(fid_int)
        if not fx:
            pending += 1
            # store snapshot as missing (keep diagnostic)
            try:
                upsert_result(fid_int, final_score=None, result_1x2=None, status=fx_status or "NO_DATA", raw={})
            except Exception:
                pass

            if fx_status == "NO_PROVIDER_KEY":
                lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ❓ nincs API kulcs beállítva (SPORTS_API_KEY / SPORTSDATAIO_API)")
            else:
                lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ❓ nincs adat (API, {fx_status})")
            continue

        provider = _detect_provider()
        score = _format_score(fx)

        if provider == "sportsdataio":
            short = (fx.get("Status") or "").upper()
            if short not in {"FINAL", "FINAL/OT", "FINAL/SO", "FT"}:
                pending += 1
                try:
                    upsert_result(fid_int, final_score=score if score != "–" else None, result_1x2=None, status=short, raw=fx)
                except Exception:
                    pass
                lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ⏳ függő ({score}, status={short})")
                continue
            gh = fx.get("HomeTeamScore")
            ga = fx.get("AwayTeamScore")
        else:
            st = ((fx.get("fixture") or {}).get("status") or {})
            short = st.get("short") or ""

            if not _status_is_finished(short):
                pending += 1
                try:
                    upsert_result(fid_int, final_score=score if score != "–" else None, result_1x2=None, status=short, raw=fx)
                except Exception:
                    pass
                lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ⏳ függő ({score}, status={short})")
                continue

            goals = (fx.get("goals") or {})
            gh = goals.get("home")
            ga = goals.get("away")

        res = _result_1x2(gh, ga)
        sel = _pick_to_1x2(pick)

        if not res or not sel:
            pending += 1
            try:
                upsert_result(fid_int, final_score=score if score != "–" else None, result_1x2=res, status=short, raw=fx)
            except Exception:
                pass
            lines.append(f"{i}. {match_label}\nTipp: {pick}\nEredmény: ❓ nem értelmezhető ({score})")
            continue

        # finished -> persist result
        try:
            upsert_result(fid_int, final_score=score if score != "–" else None, result_1x2=res, status=short, raw=fx)
        except Exception:
            pass

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

    date_iso = datetime.date.today().isoformat()
    today = datetime.date.today().strftime("%Y.%m.%d.")
    slot_text = "délelőtt / nappal" if slot == "DAY" else "délután / este"

    # Fallback schedule runs the same recap multiple times; avoid duplicate Telegram sends.
    if _should_skip_due_to_marker(slot, date_iso):
        print(f"Recap already sent for {slot} on {date_iso}; skipping.")
        return

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

    ok = True
    if vip_chat_id:
        ok_v, err_v = send_telegram_message(telegram_token, vip_chat_id, vip_msg, f"VIP_RECAP_{slot}")
        if not ok_v:
            ok = False
            print(f"VIP recap send failed: {err_v}")
    if public_chat_id:
        ok_p, err_p = send_telegram_message(telegram_token, public_chat_id, pub_msg, f"PUBLIC_RECAP_{slot}")
        if not ok_p:
            ok = False
            print(f"Public recap send failed: {err_p}")

    if ok:
        _mark_sent(slot, date_iso)
        print(f"Marked recap as sent: slot={slot} date={date_iso}")


if __name__ == "__main__":
    main()
